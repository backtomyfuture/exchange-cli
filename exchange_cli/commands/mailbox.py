"""exchange-cli mailbox {oof, tips, delegates, rules}."""

from datetime import datetime, timezone
from pathlib import Path

import click
from exchangelib import EWSDateTime, EWSTimeZone, HTMLBody

from ..core.cli import get_account
from ..core.errors import classify_exception, classify_write_exception
from ..core.io import resolve_body
from ..core.mailbox_service import (
    MAIL_TIP_REQUESTS,
    OOF_EXTERNAL_AUDIENCES,
    OOF_STATES,
    build_oof_settings,
    build_rule,
    delete_rule,
    find_rule,
    get_mail_tips,
    load_rule_spec,
)
from ..core.output import OutputFormatter
from ..core.serializers import serialize_delegate, serialize_mail_tip, serialize_oof_settings, serialize_rule
from ..core.validation import require_confirmation


def get_connection(ctx):
    return get_account(ctx)


def _rule_id(value: str) -> str:
    if not value.strip():
        raise click.BadParameter("Rule id cannot be empty.", param_hint="rule_id")
    return value.strip()


def _parse_oof_datetime(value: str) -> EWSDateTime:
    normalized = value.strip()
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise click.BadParameter(
            "Use RFC 3339 / ISO format (for example 2026-10-01T09:00:00Z) or YYYY-MM-DD HH:MM."
        ) from exc
    if parsed.tzinfo is not None:
        return EWSDateTime.from_datetime(parsed.astimezone(timezone.utc))
    return EWSDateTime.from_datetime(parsed).replace(tzinfo=EWSTimeZone.localzone())


@click.group("mailbox")
@click.pass_context
def mailbox(ctx):
    """Mailbox-wide mail settings."""


@mailbox.group("oof")
@click.pass_context
def oof(ctx):
    """Out-of-office automatic reply settings."""


@oof.command("get")
@click.pass_context
def oof_get(ctx):
    """Read the current out-of-office automatic reply settings."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        formatter.success(serialize_oof_settings(account.oof_settings))
    except Exception as exc:
        raise classify_exception(exc) from exc


@oof.command("set")
@click.option(
    "--state",
    type=click.Choice(tuple(OOF_STATES), case_sensitive=False),
    required=True,
    help="Whether OOF is enabled, scheduled, or disabled",
)
@click.option(
    "--external-audience",
    type=click.Choice(tuple(OOF_EXTERNAL_AUDIENCES), case_sensitive=False),
    default="all",
    show_default=True,
    help="Which external senders receive an automatic reply",
)
@click.option("--start", default=None, help="Scheduled OOF start (RFC 3339 or YYYY-MM-DD HH:MM)")
@click.option("--end", default=None, help="Scheduled OOF end (RFC 3339 or YYYY-MM-DD HH:MM)")
@click.option("--internal-reply", default=None, help="Automatic reply sent to internal senders")
@click.option(
    "--internal-reply-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read the internal automatic reply from a UTF-8 file",
)
@click.option("--external-reply", default=None, help="Automatic reply sent to external senders")
@click.option(
    "--external-reply-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read the external automatic reply from a UTF-8 file",
)
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Automatic reply body type")
@click.option("--dry-run", is_flag=True, default=False, help="Validate settings without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm changing automatic reply behavior")
@click.pass_context
def oof_set(
    ctx,
    state,
    external_audience,
    start,
    end,
    internal_reply,
    internal_reply_file,
    external_reply,
    external_reply_file,
    body_type,
    dry_run,
    confirm,
):
    """Set out-of-office automatic replies for the configured mailbox."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    start_value = _parse_oof_datetime(start) if start else None
    end_value = _parse_oof_datetime(end) if end else None
    internal_value = resolve_body(internal_reply, internal_reply_file, required=False)
    external_value = resolve_body(external_reply, external_reply_file, required=False)
    if body_type == "html":
        internal_value = HTMLBody(internal_value) if internal_value is not None else None
        external_value = HTMLBody(external_value) if external_value is not None else None
    settings = build_oof_settings(
        state=state.lower(),
        external_audience=external_audience.lower(),
        start=start_value,
        end=end_value,
        internal_reply=internal_value,
        external_reply=external_value,
    )

    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "mailbox.oof.set",
                "preview": {
                    "state": settings.state,
                    "external_audience": settings.external_audience,
                    "start": settings.start.isoformat() if settings.start else None,
                    "end": settings.end.isoformat() if settings.end else None,
                    "body_type": body_type,
                    "internal_reply_length": len(str(settings.internal_reply or "")),
                    "external_reply_length": len(str(settings.external_reply or "")),
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="mailbox.oof.set")
    try:
        account = get_connection(ctx)
        account.oof_settings = settings
        formatter.success(
            {
                "message": "Out-of-office settings updated",
                "state": settings.state,
                "external_audience": settings.external_audience,
                "start": settings.start.isoformat() if settings.start else None,
                "end": settings.end.isoformat() if settings.end else None,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@mailbox.group("tips")
@click.pass_context
def tips(ctx):
    """Delivery, quota, moderation, and automatic-reply checks for recipients."""


@tips.command("get")
@click.option(
    "--to",
    "recipients",
    required=True,
    multiple=True,
    help="Recipient email address; repeat for each recipient",
)
@click.option("--from", "sending_as", default=None, help="Sending address; defaults to the configured mailbox")
@click.option(
    "--request",
    "requested",
    default="All",
    type=click.Choice(MAIL_TIP_REQUESTS, case_sensitive=False),
    show_default=True,
    help="Mail-tip type to request",
)
@click.pass_context
def tips_get(ctx, recipients, sending_as, requested):
    """Read Exchange MailTips before composing or sending an email."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    canonical_request = next(value for value in MAIL_TIP_REQUESTS if value.lower() == requested.lower())
    try:
        account = get_connection(ctx)
        results = get_mail_tips(
            account,
            recipients=recipients,
            sending_as=sending_as,
            requested=canonical_request,
        )
        formatter.success([serialize_mail_tip(result) for result in results], count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@mailbox.group("delegates")
@click.pass_context
def delegates(ctx):
    """Read delegate users and their mailbox permission levels."""


@delegates.command("list")
@click.pass_context
def delegates_list(ctx):
    """List mailbox delegates exposed by exchangelib's GetDelegate API."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results = [serialize_delegate(delegate) for delegate in account.delegates]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@mailbox.group("rules")
@click.pass_context
def rules(ctx):
    """Manage server-side inbox rules using declarative JSON specifications."""


@rules.command("list")
@click.pass_context
def rules_list(ctx):
    """List inbox rules and reusable JSON ``spec`` values."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results = [serialize_rule(rule) for rule in account.rules]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@rules.command("get")
@click.argument("rule_id")
@click.pass_context
def rules_get(ctx, rule_id):
    """Read one inbox rule by its id."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    rule_id = _rule_id(rule_id)
    try:
        account = get_connection(ctx)
        formatter.success(serialize_rule(find_rule(account, rule_id)))
    except Exception as exc:
        raise classify_exception(exc) from exc


@rules.command("create")
@click.option(
    "--spec-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="UTF-8 JSON rule specification",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate the rule specification without changing Exchange",
)
@click.option("--confirm", is_flag=True, help="Confirm creating a server-side inbox rule")
@click.pass_context
def rules_create(ctx, spec_file, dry_run, confirm):
    """Create an inbox rule; folder actions are resolved against this mailbox."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    spec = load_rule_spec(spec_file, creating=True)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "mailbox.rules.create",
                "preview": {
                    "spec": spec,
                    "folder_references_resolved": False,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="mailbox.rules.create")
    try:
        account = get_connection(ctx)
        rule = build_rule(account, spec)
        account.create_rule(rule)
        formatter.success({"message": "Inbox rule created", "rule": serialize_rule(rule), "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@rules.command("update")
@click.argument("rule_id")
@click.option(
    "--spec-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="UTF-8 JSON patch; provided conditions or actions replace that entire component",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate the patch without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm changing a server-side inbox rule")
@click.pass_context
def rules_update(ctx, rule_id, spec_file, dry_run, confirm):
    """Patch an inbox rule; omitted fields retain their current values."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    rule_id = _rule_id(rule_id)
    spec = load_rule_spec(spec_file, creating=False)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "mailbox.rules.update",
                "preview": {
                    "rule_id": rule_id,
                    "patch": spec,
                    "folder_references_resolved": False,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="mailbox.rules.update")
    try:
        account = get_connection(ctx)
        rule = build_rule(account, spec, existing=find_rule(account, rule_id))
        account.set_rule(rule)
        formatter.success({"message": "Inbox rule updated", "rule": serialize_rule(rule), "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@rules.command("delete")
@click.argument("rule_id")
@click.option("--dry-run", is_flag=True, default=False, help="Preview deletion without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm deleting the inbox rule")
@click.pass_context
def rules_delete(ctx, rule_id, dry_run, confirm):
    """Delete an inbox rule, including exchangelib's disabled-rule workaround."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    rule_id = _rule_id(rule_id)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "mailbox.rules.delete",
                "preview": {"rule_id": rule_id, "requires_confirm": True},
            }
        )
        return
    require_confirmation(confirm, action="mailbox.rules.delete")
    try:
        account = get_connection(ctx)
        rule = find_rule(account, rule_id)
        deleted = serialize_rule(rule)
        delete_rule(account, rule)
        formatter.success({"message": "Inbox rule deleted", "rule": deleted, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc
