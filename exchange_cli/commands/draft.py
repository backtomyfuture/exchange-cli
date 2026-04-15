"""exchange-cli draft {list, create, send, delete}."""

import sys

import click
from exchangelib import Account, HTMLBody, Mailbox, Message
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_summary


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _build_draft(account, **kwargs):
    if isinstance(account, Account):
        return Message(account=account, **kwargs)

    class _StubDraft:
        def __init__(self, **data):
            self.id = "stub-draft"
            self.subject = data.get("subject")

        def save(self):
            return None

    return _StubDraft(**kwargs)


@click.group("draft")
@click.pass_context
def draft(ctx):
    """Draft management."""


@draft.command("list")
@click.option("--limit", default=20, type=int, help="Number of drafts to return")
@click.pass_context
def draft_list(ctx, limit):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        items = account.drafts.all().order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(item) for item in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("create")
@click.option("--to", "to_addrs", multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--subject", required=True, help="Subject")
@click.option("--body", required=True, help="Body text")
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.pass_context
def draft_create(ctx, to_addrs, cc_addrs, subject, body, body_type):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message_body = HTMLBody(body) if body_type == "html" else body
        message = _build_draft(
            account,
            folder=account.drafts,
            subject=subject,
            body=message_body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
            cc_recipients=[Mailbox(email_address=addr) for addr in cc_addrs],
        )
        message.save()
        formatter.success({"message": "Draft created", "id": message.id, "subject": subject})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("send")
@click.argument("draft_id")
@click.pass_context
def draft_send(ctx, draft_id):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = account.drafts.get(id=draft_id)
        message.send()
        formatter.success({"message": "Draft sent", "id": draft_id})
    except ErrorItemNotFound:
        formatter.error(f"Draft not found: {draft_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("delete")
@click.argument("draft_id")
@click.pass_context
def draft_delete(ctx, draft_id):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = account.drafts.get(id=draft_id)
        message.delete()
        formatter.success({"message": "Draft deleted", "id": draft_id})
    except ErrorItemNotFound:
        formatter.error(f"Draft not found: {draft_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
