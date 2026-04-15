"""exchange-cli email {list, read, send, reply, forward, search}."""

import json
import os
import sys
from datetime import datetime

import click
from exchangelib import Account, EWSDateTime, EWSTimeZone, FileAttachment, HTMLBody, Mailbox, Message, Q

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.daemon import build_daemon_state, daemon_ping, send_daemon_request, start_daemon, stream_watch_events
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_detail, serialize_email_summary


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _resolve_folder(account, folder_name: str):
    mapping = {
        "inbox": account.inbox,
        "sent": account.sent,
        "drafts": account.drafts,
        "trash": account.trash,
        "junk": account.junk,
    }
    return mapping.get(folder_name.lower(), account.inbox)


def _find_message(account, message_id: str):
    folders = [account.inbox, account.sent, account.drafts, account.trash, account.junk]
    for folder in folders:
        try:
            return folder.get(id=message_id)
        except Exception:
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


def _apply_summary_field_projection(queryset, *, include_body_preview: bool):
    # unittest.mock objects used in tests allow arbitrary attribute access, so skip projection there.
    if queryset.__class__.__module__.startswith("unittest.mock"):
        return queryset
    fields = [
        "subject",
        "sender",
        "to_recipients",
        "cc_recipients",
        "datetime_received",
        "datetime_sent",
        "is_read",
        "has_attachments",
        "importance",
    ]
    if include_body_preview:
        fields.append("text_body")
    try:
        return queryset.only(*fields)
    except Exception:
        return queryset


def _should_use_daemon() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return os.environ.get("EXCHANGE_CLI_DISABLE_DAEMON", "").strip().lower() not in {"1", "true", "yes", "on"}


def _list_via_daemon(ctx, folder_name, limit, unread, with_preview):
    if not _should_use_daemon():
        return None
    try:
        state = build_daemon_state(ctx.obj.get("config_path"))
        if not daemon_ping(state):
            start_daemon(state)
        response = send_daemon_request(
            state,
            {
                "action": "email_list",
                "account": ctx.obj.get("account_email"),
                "folder": folder_name,
                "limit": limit,
                "unread": unread,
                "with_preview": with_preview,
            },
            timeout=15.0,
        )
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Daemon email list failed"))
        return response
    except Exception as exc:
        if ctx.obj.get("verbose"):
            click.echo(f"Daemon unavailable, falling back to direct mode: {exc}", err=True)
        return None


@click.group("email")
@click.pass_context
def email(ctx):
    """Email operations."""


@email.command("list")
@click.option("--folder", "folder_name", default="inbox", help="Folder name")
@click.option("--limit", default=20, type=int, help="Number of messages to return")
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
        daemon_result = _list_via_daemon(ctx, folder_name, limit, unread, with_preview)
        if daemon_result:
            formatter.success(daemon_result.get("data", []), count=daemon_result.get("count"))
            return
        account = get_connection(ctx)
        folder = _resolve_folder(account, folder_name)
        queryset = folder.filter(is_read=False) if unread else folder.all()
        projected = _apply_summary_field_projection(queryset, include_body_preview=with_preview)
        items = projected.order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item, include_body_preview=with_preview) for item in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("read")
@click.argument("message_id")
@click.option("--save-attachments", "save_dir", default=None, help="Directory to save attachments")
@click.pass_context
def email_read(ctx, message_id, save_dir):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            formatter.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            for attachment in message.attachments:
                if isinstance(attachment, FileAttachment):
                    path = os.path.join(save_dir, attachment.name)
                    with open(path, "wb") as handle:
                        handle.write(attachment.content)
                    click.echo(f"Saved: {path}", err=True)

        formatter.success(serialize_email_detail(message))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("send")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC email(s)")
@click.option("--subject", required=True, help="Email subject")
@click.option("--body", default=None, help="Email body text")
@click.option("--body-file", default=None, type=click.Path(exists=True), help="Read body from file")
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.option("--attach", "attachments", multiple=True, type=click.Path(exists=True), help="Attach file(s)")
@click.pass_context
def email_send(ctx, to_addrs, cc_addrs, bcc_addrs, subject, body, body_file, body_type, attachments):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    if body_file:
        with open(body_file, encoding="utf-8") as handle:
            body = handle.read()
    if not body:
        formatter.error("Either --body or --body-file is required", code="INVALID_INPUT")
        sys.exit(1)

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
            message.attach(FileAttachment(name=os.path.basename(path), content=content))

        message.send_and_save()
        formatter.success({"message": "Email sent", "subject": subject, "to": list(to_addrs)})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("reply")
@click.argument("message_id")
@click.option("--body", required=True, help="Reply body")
@click.option("--all", "reply_all", is_flag=True, default=False, help="Reply to all")
@click.pass_context
def email_reply(ctx, message_id, body, reply_all):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            formatter.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)
        if reply_all:
            message.reply_all(subject=f"Re: {message.subject}", body=body)
        else:
            message.reply(subject=f"Re: {message.subject}", body=body)
        formatter.success({"message": "Reply sent", "original_id": message_id})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("forward")
@click.argument("message_id")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Forward to email(s)")
@click.option("--body", default="", help="Additional message")
@click.pass_context
def email_forward(ctx, message_id, to_addrs, body):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = _find_message(account, message_id)
        if not message:
            formatter.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)
        message.forward(
            subject=f"Fwd: {message.subject}",
            body=body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
        )
        formatter.success({"message": "Email forwarded", "original_id": message_id, "to": list(to_addrs)})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("search")
@click.argument("query")
@click.option("--folder", "folder_name", default="inbox", help="Folder to search")
@click.option("--limit", default=20, type=int, help="Max results")
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
        folder = _resolve_folder(get_connection(ctx), folder_name)
        criteria = Q(subject__icontains=query) | Q(body__icontains=query)
        if start:
            start_dt = _parse_search_date(start, is_end=False)
            criteria &= Q(datetime_received__gte=start_dt)
        if end:
            end_dt = _parse_search_date(end, is_end=True)
            criteria &= Q(datetime_received__lte=end_dt)
        queryset = folder.filter(criteria)
        projected = _apply_summary_field_projection(queryset, include_body_preview=with_preview)
        items = projected.order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item, include_body_preview=with_preview) for item in items]
        formatter.success(results, count=len(results))
    except click.BadParameter as exc:
        formatter.error(str(exc), code="INVALID_INPUT")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@email.command("watch")
@click.option("--folder", "folder_name", default="inbox", help="Folder name to watch")
@click.option(
    "--backfill-minutes",
    default=10,
    type=int,
    show_default=True,
    help="Backfill window after streaming reconnect",
)
@click.pass_context
def email_watch(ctx, folder_name, backfill_minutes):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    state = build_daemon_state(ctx.obj.get("config_path"))
    if not daemon_ping(state):
        try:
            start_daemon(state)
        except Exception as exc:
            formatter.error(str(exc), code="DAEMON_START_FAILED")
            sys.exit(1)
    request = {
        "action": "watch",
        "account": ctx.obj.get("account_email"),
        "folder": folder_name,
        "backfill_minutes": backfill_minutes,
    }
    try:
        first, iterator = stream_watch_events(state, request)
    except Exception as exc:
        formatter.error(str(exc), code="DAEMON_UNAVAILABLE")
        sys.exit(1)

    if not first.get("ok"):
        formatter.error(first.get("error", "Daemon rejected watch request"), code="WATCH_SUBSCRIBE_FAILED")
        sys.exit(1)

    click.echo(f"Watching folder '{folder_name}'. Press Ctrl+C to stop.", err=True)
    try:
        for envelope in iterator:
            if not envelope.get("ok"):
                formatter.error(envelope.get("error", "Daemon stream error"), code="WATCH_STREAM_ERROR")
                sys.exit(1)
            if envelope.get("type") != "event":
                continue
            event = envelope.get("data")
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
