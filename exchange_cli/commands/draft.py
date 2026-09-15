"""exchange-cli draft {list, create, send, delete}."""

from pathlib import Path

import click
from exchangelib import FileAttachment, HTMLBody, Mailbox, Message
from exchangelib.errors import ErrorItemNotFound

from ..core.cli import get_account
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.io import resolve_body
from ..core.output import OutputFormatter
from ..core.query import take_page
from ..core.serializers import serialize_email_summary
from ..core.validation import MAX_RESULTS, parse_inline_attachment, require_confirmation


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
@click.option("--from", "from_addr", default=None, help="Sender email (author)")
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
@click.option("--dry-run", is_flag=True, default=False, help="Simulate draft creation without connecting or saving")
@click.pass_context
def draft_create(
    ctx,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    from_addr,
    subject,
    body,
    body_file,
    body_type,
    attachments,
    inline_attachments,
    dry_run,
):
    """Create a draft message without sending."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file)
    parsed_inline = [parse_inline_attachment(item) for item in inline_attachments]
    if dry_run:
        attachment_previews = [{"name": p.name, "size": p.stat().st_size if p.is_file() else None} for p in attachments]
        inline_attachment_previews = [
            {"name": p.name, "size": p.stat().st_size if p.is_file() else None, "content_id": cid}
            for p, cid in parsed_inline
        ]
        formatter.success(
            {
                "dry_run": True,
                "action": "draft.create",
                "preview": {
                    "to": list(to_addrs),
                    "cc": list(cc_addrs),
                    "bcc": list(bcc_addrs),
                    "from": from_addr,
                    "subject": subject,
                    "body_type": body_type,
                    "body_length": len(body),
                    "attachments": attachment_previews,
                    "inline_attachments": inline_attachment_previews,
                    "requires_confirm": False,
                },
            }
        )
        return

    try:
        account = get_connection(ctx)
        message_body = HTMLBody(body) if body_type == "html" else body
        author = Mailbox(email_address=from_addr) if from_addr else None
        message = Message(
            account=account,
            folder=account.drafts,
            subject=subject,
            body=message_body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
            cc_recipients=[Mailbox(email_address=addr) for addr in cc_addrs],
            bcc_recipients=[Mailbox(email_address=addr) for addr in bcc_addrs],
            author=author,
        )
        _attach_files(message, attachments, parsed_inline)
        message.save()
        formatter.success({"message": "Draft created", "id": message.id, "subject": subject, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@draft.command("send")
@click.argument("draft_id")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate sending draft without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the draft")
@click.pass_context
def draft_send(ctx, draft_id, dry_run, confirm):
    """Send an existing draft message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "draft.send",
                "preview": {
                    "draft_id": draft_id,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="draft.send")
    try:
        account = get_connection(ctx)
        message = account.drafts.get(id=draft_id)
        message.send()
        formatter.success({"message": "Draft sent", "id": draft_id, "outcome": "succeeded"})
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
