"""exchange-cli draft {list, create, update, send, delete}."""

from pathlib import Path

import click
from exchangelib import FileAttachment, HTMLBody, Mailbox, Message
from exchangelib.errors import ErrorItemNotFound

from ..core.cli import get_account
from ..core.email_service import resolve_mail_folder
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.html_sanitizer import sanitize_draft_html
from ..core.io import resolve_body
from ..core.output import OutputFormatter
from ..core.query import take_page
from ..core.serializers import serialize_email_summary
from ..core.validation import MAX_RESULTS, parse_inline_attachment, require_confirmation
from .email import IMPORTANCE_VALUES, SENSITIVITY_VALUES, _mailboxes, email_update


def get_connection(ctx):
    return get_account(ctx)


def _attach_files(message, attachments, inline_attachments=None) -> None:
    for path in attachments or []:
        with open(path, "rb") as handle:
            content = handle.read()
        message.attach(FileAttachment(name=path.name, content=content))
    for path, cid in inline_attachments or []:
        with open(path, "rb") as handle:
            content = handle.read()
        message.attach(FileAttachment(name=path.name, content=content, is_inline=True, content_id=cid))


@click.group("draft")
@click.pass_context
def draft(ctx):
    """Draft management."""


@draft.command("list")
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Number of drafts to return")
@click.pass_context
def draft_list(ctx, limit):
    """List draft messages."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        page, truncated = take_page(account.drafts.all().order_by("-datetime_received"), limit)
        results = [serialize_email_summary(item) for item in page]
        formatter.success(results, count=len(results), truncated=truncated)
    except Exception as exc:
        raise classify_exception(exc) from exc


@draft.command("create")
@click.option("--to", "to_addrs", multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC email(s)")
@click.option("--reply-to", "reply_to_addrs", multiple=True, help="Reply-To email(s)")
@click.option("--from", "from_addr", default=None, help="Sender email (author)")
@click.option("--category", "categories", multiple=True, help="Message category or categories")
@click.option(
    "--importance",
    type=click.Choice(tuple(IMPORTANCE_VALUES), case_sensitive=False),
    default=None,
    help="Message importance",
)
@click.option(
    "--sensitivity",
    type=click.Choice(tuple(SENSITIVITY_VALUES), case_sensitive=False),
    default=None,
    help="Message sensitivity",
)
@click.option("--read-receipt", is_flag=True, default=False, help="Request a read receipt on send")
@click.option("--delivery-receipt", is_flag=True, default=False, help="Request a delivery receipt on send")
@click.option("--response-requested", is_flag=True, default=False, help="Request a response on send")
@click.option("--subject", required=True, help="Subject")
@click.option("--body", default=None, help="Body text")
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
@click.option(
    "--inline-attach",
    "inline_attachments",
    multiple=True,
    help="Attach inline file(s) in format 'path[:cid]'",
)
@click.option(
    "--no-sanitize",
    is_flag=True,
    default=False,
    help="Skip HTML sanitization for Outlook compatibility",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate draft creation without connecting or saving")
@click.pass_context
def draft_create(
    ctx,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    reply_to_addrs,
    from_addr,
    categories,
    importance,
    sensitivity,
    read_receipt,
    delivery_receipt,
    response_requested,
    subject,
    body,
    body_file,
    body_type,
    attachments,
    inline_attachments,
    no_sanitize,
    dry_run,
):
    """Create a draft message without sending."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file)
    parsed_inline = [parse_inline_attachment(item) for item in inline_attachments]

    sanitized = False
    sanitized_rules = []
    if body_type == "html" and not no_sanitize and body:
        cleaned_body, sanitized_rules = sanitize_draft_html(body)
        sanitized = bool(sanitized_rules)
    else:
        cleaned_body = body

    if dry_run:
        attachment_previews = [{"name": p.name, "size": p.stat().st_size if p.is_file() else None} for p in attachments]
        inline_attachment_previews = [
            {"name": p.name, "size": p.stat().st_size if p.is_file() else None, "content_id": cid}
            for p, cid in parsed_inline
        ]
        preview_data = {
            "to": list(to_addrs),
            "cc": list(cc_addrs),
            "bcc": list(bcc_addrs),
            "reply_to": list(reply_to_addrs),
            "from": from_addr,
            "subject": subject,
            "body_type": body_type,
            "body_length": len(cleaned_body or ""),
            "categories": list(categories),
            "importance": importance.lower() if importance else None,
            "sensitivity": sensitivity.lower() if sensitivity else None,
            "read_receipt": read_receipt,
            "delivery_receipt": delivery_receipt,
            "response_requested": response_requested,
            "attachments": attachment_previews,
            "inline_attachments": inline_attachment_previews,
            "requires_confirm": False,
            "sanitized": sanitized,
        }
        if sanitized_rules:
            preview_data["sanitized_rules"] = sanitized_rules
        formatter.success(
            {
                "dry_run": True,
                "action": "draft.create",
                "preview": preview_data,
            }
        )
        return

    try:
        account = get_connection(ctx)
        message_body = HTMLBody(cleaned_body) if body_type == "html" else cleaned_body
        author = Mailbox(email_address=from_addr) if from_addr else None
        message_kwargs = {
            "account": account,
            "folder": account.drafts,
            "subject": subject,
            "body": message_body,
            "to_recipients": _mailboxes(to_addrs),
            "cc_recipients": _mailboxes(cc_addrs),
            "bcc_recipients": _mailboxes(bcc_addrs),
            "reply_to": _mailboxes(reply_to_addrs),
            "author": author,
            "categories": list(categories),
        }
        if importance is not None:
            message_kwargs["importance"] = IMPORTANCE_VALUES[importance.lower()]
        if sensitivity is not None:
            message_kwargs["sensitivity"] = SENSITIVITY_VALUES[sensitivity.lower()]
        if read_receipt:
            message_kwargs["is_read_receipt_requested"] = True
        if delivery_receipt:
            message_kwargs["is_delivery_receipt_requested"] = True
        if response_requested:
            message_kwargs["is_response_requested"] = True
        message = Message(**message_kwargs)
        _attach_files(message, attachments, parsed_inline)
        message.save()
        result_payload = {
            "message": "Draft created",
            "id": message.id,
            "changekey": getattr(message, "changekey", None),
            "subject": subject,
            "sanitized": sanitized,
            "outcome": "succeeded",
        }
        if sanitized_rules:
            result_payload["sanitized_rules"] = sanitized_rules
        formatter.success(result_payload)
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@draft.command("send")
@click.argument("draft_id")
@click.option("--save-copy/--no-save-copy", default=True, help="Save a copy in Sent Items")
@click.option("--sent-folder", default=None, help="Folder in which to save the sent copy")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate sending draft without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the draft")
@click.pass_context
def draft_send(ctx, draft_id, save_copy, sent_folder, dry_run, confirm):
    """Send an existing draft message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if sent_folder is not None and not save_copy:
        raise CliError(
            "--sent-folder requires --save-copy.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "draft.send",
                "preview": {
                    "draft_id": draft_id,
                    "save_copy": save_copy,
                    "sent_folder": sent_folder,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="draft.send")
    try:
        account = get_connection(ctx)
        message = account.drafts.get(id=draft_id)
        sent_copy_folder = resolve_mail_folder(account, sent_folder) if sent_folder else None
        message.send(save_copy=save_copy, copy_to_folder=sent_copy_folder)
        formatter.success(
            {
                "message": "Draft sent",
                "id": draft_id,
                "saved_copy": save_copy,
                "sent_folder": sent_folder,
                "outcome": "succeeded",
            }
        )
    except ErrorItemNotFound as exc:
        raise CliError(f"Draft not found: {draft_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@draft.command("delete")
@click.argument("draft_id")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate deleting draft without connecting or deleting")
@click.option("--confirm", is_flag=True, help="Confirm permanent deletion")
@click.pass_context
def draft_delete(ctx, draft_id, dry_run, confirm):
    """Delete a draft message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "draft.delete",
                "preview": {
                    "draft_id": draft_id,
                    "permanent": True,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="draft.delete")
    try:
        account = get_connection(ctx)
        message = account.drafts.get(id=draft_id)
        message.delete()
        formatter.success({"message": "Draft deleted", "id": draft_id, "permanent": True, "outcome": "succeeded"})
    except ErrorItemNotFound as exc:
        raise CliError(f"Draft not found: {draft_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc


# Reuse the full message update contract while making the intent explicit in
# the command path. The callback checks the parent group and rejects a
# non-draft item before any write is attempted.
draft.add_command(email_update, "update")
