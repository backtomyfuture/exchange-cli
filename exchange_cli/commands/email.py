"""exchange-cli email {list, read, send, reply, forward, search}."""

import os
import sys
from datetime import datetime

import click
from exchangelib import Account, EWSDateTime, EWSTimeZone, FileAttachment, HTMLBody, Mailbox, Message, Q

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
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


@click.group("email")
@click.pass_context
def email(ctx):
    """Email operations."""


@email.command("list")
@click.option("--folder", "folder_name", default="inbox", help="Folder name")
@click.option("--limit", default=20, type=int, help="Number of messages to return")
@click.option("--unread", is_flag=True, default=False, help="Only unread messages")
@click.pass_context
def email_list(ctx, folder_name, limit, unread):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        folder = _resolve_folder(account, folder_name)
        queryset = folder.filter(is_read=False) if unread else folder.all()
        items = queryset.order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item) for item in items]
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
@click.pass_context
def email_search(ctx, query, folder_name, limit, start, end):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        folder = _resolve_folder(get_connection(ctx), folder_name)
        criteria = Q(subject__icontains=query) | Q(body__icontains=query)
        timezone = EWSTimeZone.localzone()
        if start:
            start_dt = timezone.localize(EWSDateTime.from_datetime(datetime.strptime(start, "%Y-%m-%d")))
            criteria &= Q(datetime_received__gte=start_dt)
        if end:
            end_dt = timezone.localize(EWSDateTime.from_datetime(datetime.strptime(end, "%Y-%m-%d")))
            criteria &= Q(datetime_received__lte=end_dt)
        items = folder.filter(criteria).order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item) for item in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
