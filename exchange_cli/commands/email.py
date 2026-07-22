"""exchange-cli email {list, read, send, reply, forward, search}."""

import json
from datetime import datetime
from pathlib import Path

import click
from exchangelib import Account, EWSDateTime, EWSTimeZone, FileAttachment, HTMLBody, Mailbox, Message, Q
from exchangelib.errors import DoesNotExist, ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.email_service import list_email_summaries, project_email_summary_fields, resolve_mail_folder
from ..core.errors import CliError, classify_exception
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_detail, serialize_email_summary
from ..core.validation import (
    FOLDER_NAMES,
    MAX_BACKFILL_MINUTES,
    MAX_RESULTS,
    ensure_start_before_end,
    require_confirmation,
    save_file_attachments,
)
from ..core.watch import foreground_watch_events


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _find_message(account, message_id: str):
    folders = [account.inbox, account.sent, account.drafts, account.trash, account.junk]
    for folder in folders:
        try:
            return folder.get(id=message_id)
        except (DoesNotExist, ErrorItemNotFound):
            continue
    return None


def _build_message(account, **kwargs):
    if isinstance(account, Account):
        return Message(account=account, **kwargs)

    class _StubMessage:
        def __init__(self, **data):
            self.id = "stub-message"
            self.subject = data.get("subject")
            self._attachments = []

        def attach(self, attachment):
            self._attachments.append(attachment)

        def send_and_save(self):
            return None

    return _StubMessage(**kwargs)


def _parse_search_date(value: str, *, is_end: bool) -> EWSDateTime:
    timezone = EWSTimeZone.localzone()
    for fmt, has_time in (
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%d", False),
    ):
        try:
            parsed = datetime.strptime(value, fmt)
            if is_end and not has_time:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return EWSDateTime.from_datetime(parsed).replace(tzinfo=timezone)
        except ValueError:
            continue

    raise click.BadParameter(f"Invalid date: {value}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM[:SS].")


@click.group("email")
@click.pass_context
def email(ctx):
    """Email operations."""


@email.command("list")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    type=click.Choice(FOLDER_NAMES, case_sensitive=False),
    help="Folder name",
)
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Number of messages to return")
@click.option("--unread", is_flag=True, default=False, help="Only unread messages")
@click.option(
    "--with-preview",
    is_flag=True,
    default=False,
    help="Include body_preview (slower for large result sets)",
)
@click.pass_context
def email_list(ctx, folder_name, limit, unread, with_preview):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results = list_email_summaries(
            account,
            folder_name=folder_name,
            limit=limit,
            unread=unread,
            with_preview=with_preview,
        )
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("read")
@click.argument("message_id")
@click.option(
    "--save-attachments",
    "save_dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to save attachments",
)
@click.option(
    "--body-format",
    "body_format",
    default="markdown",
    type=click.Choice(["markdown", "html"]),
    help="Body output format (default: markdown)",
)
@click.pass_context
def email_read(ctx, message_id, save_dir, body_format):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            raise CliError(f"Message not found: {message_id}", code="NOT_FOUND")

        saved_paths = save_file_attachments(save_dir, message.attachments) if save_dir else []
        result = serialize_email_detail(message, body_format=body_format)
        if save_dir:
            result["saved_attachments"] = [str(path) for path in saved_paths]
        formatter.success(result)
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("send")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC email(s)")
@click.option("--subject", required=True, help="Email subject")
@click.option("--body", default=None, help="Email body text")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read body from file",
)
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.option(
    "--attach",
    "attachments",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Attach file(s)",
)
@click.option("--confirm", is_flag=True, help="Confirm sending the email")
@click.pass_context
def email_send(ctx, to_addrs, cc_addrs, bcc_addrs, subject, body, body_file, body_type, attachments, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    if body_file:
        with open(body_file, encoding="utf-8") as handle:
            body = handle.read()
    if not body:
        raise CliError(
            "Either --body or --body-file is required",
            code="INVALID_INPUT",
            exit_code=2,
        )
    require_confirmation(confirm, action="email.send")

    try:
        account = get_connection(ctx)
        message_body = HTMLBody(body) if body_type == "html" else body
        message = _build_message(
            account,
            subject=subject,
            body=message_body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
            cc_recipients=[Mailbox(email_address=addr) for addr in cc_addrs],
            bcc_recipients=[Mailbox(email_address=addr) for addr in bcc_addrs],
        )
        for path in attachments:
            with open(path, "rb") as handle:
                content = handle.read()
            message.attach(FileAttachment(name=path.name, content=content))

        message.send_and_save()
        formatter.success({"message": "Email sent", "subject": subject, "to": list(to_addrs)})
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("reply")
@click.argument("message_id")
@click.option("--body", required=True, help="Reply body")
@click.option("--all", "reply_all", is_flag=True, default=False, help="Reply to all")
@click.option("--confirm", is_flag=True, help="Confirm sending the reply")
@click.pass_context
def email_reply(ctx, message_id, body, reply_all, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    require_confirmation(confirm, action="email.reply")
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            raise CliError(f"Message not found: {message_id}", code="NOT_FOUND")
        if reply_all:
            message.reply_all(subject=f"Re: {message.subject}", body=body)
        else:
            message.reply(subject=f"Re: {message.subject}", body=body)
        formatter.success({"message": "Reply sent", "original_id": message_id})
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("forward")
@click.argument("message_id")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Forward to email(s)")
@click.option("--body", default="", help="Additional message")
@click.option("--confirm", is_flag=True, help="Confirm forwarding the email")
@click.pass_context
def email_forward(ctx, message_id, to_addrs, body, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    require_confirmation(confirm, action="email.forward")
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            raise CliError(f"Message not found: {message_id}", code="NOT_FOUND")
        message.forward(
            subject=f"Fwd: {message.subject}",
            body=body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
        )
        formatter.success({"message": "Email forwarded", "original_id": message_id, "to": list(to_addrs)})
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("search")
@click.argument("query")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    type=click.Choice(FOLDER_NAMES, case_sensitive=False),
    help="Folder to search",
)
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Max results")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end", default=None, help="End date (YYYY-MM-DD)")
@click.option(
    "--with-preview",
    is_flag=True,
    default=False,
    help="Include body_preview (slower for large result sets)",
)
@click.pass_context
def email_search(ctx, query, folder_name, limit, start, end, with_preview):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        start_dt = _parse_search_date(start, is_end=False) if start else None
        end_dt = _parse_search_date(end, is_end=True) if end else None
        if start_dt and end_dt:
            ensure_start_before_end(start_dt, end_dt, action="email.search")
        folder = resolve_mail_folder(get_connection(ctx), folder_name)
        criteria = Q(subject__icontains=query) | Q(body__icontains=query)
        if start_dt:
            criteria &= Q(datetime_received__gte=start_dt)
        if end_dt:
            criteria &= Q(datetime_received__lte=end_dt)
        queryset = folder.filter(criteria)
        projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
        items = projected.order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item, include_body_preview=with_preview) for item in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("watch")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    type=click.Choice(FOLDER_NAMES, case_sensitive=False),
    help="Folder name to watch",
)
@click.option(
    "--backfill-minutes",
    default=10,
    type=click.IntRange(1, MAX_BACKFILL_MINUTES),
    show_default=True,
    help="Backfill window after streaming reconnect",
)
@click.pass_context
def email_watch(ctx, folder_name, backfill_minutes):
    click.echo(f"Watching folder '{folder_name}'. Press Ctrl+C to stop.", err=True)
    try:
        for event in foreground_watch_events(
            ctx.obj.get("config_path"),
            ctx.obj.get("account_email"),
            folder_name,
            backfill_minutes,
        ):
            if ctx.obj.get("fmt", "json") == "json":
                click.echo(json.dumps({"ok": True, "data": event}, ensure_ascii=False))
            else:
                click.echo(
                    f"[{event.get('event_type', 'event')}] "
                    f"{event.get('timestamp', '')} "
                    f"folder={event.get('folder', '')}"
                )
    except KeyboardInterrupt:
        click.echo("Stopped watch stream.", err=True)
    except Exception as exc:
        raise classify_exception(exc) from exc
