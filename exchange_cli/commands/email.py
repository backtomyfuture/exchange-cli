"""exchange-cli email {list, read, send, reply, forward, search, mark-read, move, delete, watch}."""

import json
import signal
from datetime import datetime, timezone
from pathlib import Path

import click
from exchangelib import EWSDateTime, EWSTimeZone, FileAttachment, HTMLBody, Mailbox, Message, Q

from ..core.cli import get_account
from ..core.email_service import (
    _validate_folder_input,
    archive_message,
    copy_message,
    delete_message,
    find_message,
    list_email_summaries,
    move_message,
    project_email_summary_fields,
    require_message,
    resolve_mail_folder,
    scan_email_page,
    set_message_junk_state,
    set_message_read_state,
    update_message,
)
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.html_sanitizer import sanitize_draft_html
from ..core.io import resolve_body
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_detail, serialize_email_summary
from ..core.validation import (
    EMAIL_DETAIL_FIELD_CHOICES,
    MAX_BACKFILL_MINUTES,
    MAX_RESULTS,
    MAX_WATCH_DURATION_SECONDS,
    MAX_WATCH_EVENTS,
    ensure_start_before_end,
    parse_field_list,
    parse_inline_attachment,
    require_confirmation,
    save_file_attachments,
)
from ..core.watch import foreground_watch_events


def get_connection(ctx):
    return get_account(ctx)


def _find_message(account, message_id: str):
    return find_message(account, message_id)


def _parse_search_date(value: str, *, is_end: bool) -> EWSDateTime:
    val = value.strip()
    iso_val = val.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_val)
        has_time = "T" in val or " " in val
        if is_end and not has_time:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        if parsed.tzinfo is not None:
            return EWSDateTime.from_datetime(parsed.astimezone(timezone.utc))
        return EWSDateTime.from_datetime(parsed).replace(tzinfo=EWSTimeZone.localzone())
    except ValueError:
        pass

    timezone_local = EWSTimeZone.localzone()
    for fmt, has_time in (
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%d", False),
    ):
        try:
            parsed = datetime.strptime(val, fmt)
            if is_end and not has_time:
                parsed = parsed.replace(hour=23, minute=59, second=59)
            return EWSDateTime.from_datetime(parsed).replace(tzinfo=timezone_local)
        except ValueError:
            continue

    raise click.BadParameter(
        f"Invalid date: {value}. Use RFC 3339 / ISO format (e.g. 2026-09-12T10:00:00Z) or YYYY-MM-DD [HH:MM[:SS]]."
    )


def _require_folder_arg(folder_name: str) -> str:
    return _validate_folder_input(folder_name)


def _attach_files(message, attachments, inline_attachments=None) -> None:
    for path in attachments or []:
        with open(path, "rb") as handle:
            content = handle.read()
        message.attach(FileAttachment(name=path.name, content=content))
    for path, cid in inline_attachments or []:
        with open(path, "rb") as handle:
            content = handle.read()
        message.attach(FileAttachment(name=path.name, content=content, is_inline=True, content_id=cid))


IMPORTANCE_VALUES = {"low": "Low", "normal": "Normal", "high": "High"}
SENSITIVITY_VALUES = {
    "normal": "Normal",
    "personal": "Personal",
    "private": "Private",
    "confidential": "Confidential",
}
CONFLICT_RESOLUTION_VALUES = {
    "auto-resolve": "AutoResolve",
    "always-overwrite": "AlwaysOverwrite",
    "never-overwrite": "NeverOverwrite",
}
DRAFT_ONLY_UPDATE_FIELDS = {
    "author",
    "bcc_recipients",
    "cc_recipients",
    "is_delivery_receipt_requested",
    "is_read_receipt_requested",
    "is_response_requested",
    "reply_to",
    "to_recipients",
}


def _mailboxes(addresses):
    return [Mailbox(email_address=address) for address in addresses]


def _set_recipient_update(values, *, field, addresses, clear):
    if addresses and clear:
        raise CliError(
            f"Use either --{field.removesuffix('_recipients').replace('_', '-')} or its clear option, not both.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if addresses:
        values[field] = _mailboxes(addresses)
    elif clear:
        values[field] = []


def _build_message_update_values(
    *,
    subject,
    body,
    body_file,
    body_type,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    reply_to_addrs,
    clear_to,
    clear_cc,
    clear_bcc,
    clear_reply_to,
    from_addr,
    categories,
    clear_categories,
    importance,
    sensitivity,
    is_read,
    read_receipt_requested,
    delivery_receipt_requested,
    response_requested,
    no_sanitize=False,
):
    values = {}
    if subject is not None:
        values["subject"] = subject
    if body is not None or body_file is not None:
        resolved_body = resolve_body(body, body_file, required=False)
        if body_type == "html" and not no_sanitize and resolved_body:
            resolved_body, _ = sanitize_draft_html(resolved_body)
        values["body"] = HTMLBody(resolved_body or "") if body_type == "html" else (resolved_body or "")

    _set_recipient_update(values, field="to_recipients", addresses=to_addrs, clear=clear_to)
    _set_recipient_update(values, field="cc_recipients", addresses=cc_addrs, clear=clear_cc)
    _set_recipient_update(values, field="bcc_recipients", addresses=bcc_addrs, clear=clear_bcc)
    _set_recipient_update(values, field="reply_to", addresses=reply_to_addrs, clear=clear_reply_to)

    if from_addr is not None:
        values["author"] = Mailbox(email_address=from_addr)
    if categories and clear_categories:
        raise CliError(
            "Use either --category or --clear-categories, not both.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if categories:
        values["categories"] = list(categories)
    elif clear_categories:
        values["categories"] = []
    if importance is not None:
        values["importance"] = IMPORTANCE_VALUES[importance.lower()]
    if sensitivity is not None:
        values["sensitivity"] = SENSITIVITY_VALUES[sensitivity.lower()]
    if is_read is not None:
        values["is_read"] = is_read
    if read_receipt_requested is not None:
        values["is_read_receipt_requested"] = read_receipt_requested
    if delivery_receipt_requested is not None:
        values["is_delivery_receipt_requested"] = delivery_receipt_requested
    if response_requested is not None:
        values["is_response_requested"] = response_requested
    return values


def _serialize_copy_result(value):
    if value is None:
        return {"id": None, "changekey": None}
    if isinstance(value, tuple) and len(value) == 2:
        return {"id": value[0], "changekey": value[1]}
    return {"id": getattr(value, "id", None), "changekey": getattr(value, "changekey", None)}


@click.group("email")
@click.pass_context
def email(ctx):
    """Email operations."""


@email.command("list")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    help="Well-known name, folder path, or folder id",
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
    """List messages from a well-known folder, path, or folder id."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_name = _require_folder_arg(folder_name)
    try:
        account = get_connection(ctx)
        results, truncated, skipped_items = list_email_summaries(
            account,
            folder_name=folder_name,
            limit=limit,
            unread=unread,
            with_preview=with_preview,
        )
        formatter.success(results, count=len(results), truncated=truncated, skipped_items=skipped_items)
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
@click.option(
    "--include-html",
    is_flag=True,
    default=False,
    help="Include raw body_html and unique_body_html in output",
)
@click.option(
    "--max-body-length",
    default=None,
    type=click.IntRange(1),
    help="Truncate body to maximum number of characters",
)
@click.option(
    "--fields",
    default=None,
    help="Comma-separated fields to include",
)
@click.pass_context
def email_read(ctx, message_id, save_dir, body_format, include_html, max_body_length, fields):
    """Read one message. Returns clean Markdown body by default."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        selected = parse_field_list(fields, allowed=EMAIL_DETAIL_FIELD_CHOICES)
        account = get_connection(ctx)
        message = require_message(account, message_id)
        saved_paths = save_file_attachments(save_dir, message.attachments) if save_dir else []
        result = serialize_email_detail(
            message,
            body_format=body_format,
            fields=selected,
            include_html=include_html,
            max_body_length=max_body_length,
        )
        if save_dir:
            result["saved_attachments"] = [str(path) for path in saved_paths]
        formatter.success(result)
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("send")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Recipient email(s)")
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
@click.option("--read-receipt", is_flag=True, default=False, help="Request a read receipt")
@click.option("--delivery-receipt", is_flag=True, default=False, help="Request a delivery receipt")
@click.option("--response-requested", is_flag=True, default=False, help="Request a response")
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
@click.option(
    "--inline-attach",
    "inline_attachments",
    multiple=True,
    help="Attach inline file(s) in format 'path[:cid]'",
)
@click.option("--save-copy/--no-save-copy", default=True, help="Save a copy in Sent Items")
@click.option("--sent-folder", default=None, help="Folder in which to save the sent copy")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate send without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the email")
@click.pass_context
def email_send(
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
    save_copy,
    sent_folder,
    dry_run,
    confirm,
):
    """Send a new email."""
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
                "action": "email.send",
                "preview": {
                    "to": list(to_addrs),
                    "cc": list(cc_addrs),
                    "bcc": list(bcc_addrs),
                    "reply_to": list(reply_to_addrs),
                    "from": from_addr,
                    "subject": subject,
                    "body_type": body_type,
                    "body_length": len(body),
                    "categories": list(categories),
                    "importance": importance.lower() if importance else None,
                    "sensitivity": sensitivity.lower() if sensitivity else None,
                    "read_receipt": read_receipt,
                    "delivery_receipt": delivery_receipt,
                    "response_requested": response_requested,
                    "save_copy": save_copy,
                    "sent_folder": sent_folder,
                    "attachments": attachment_previews,
                    "inline_attachments": inline_attachment_previews,
                    "requires_confirm": True,
                },
            }
        )
        return
    if sent_folder is not None and not save_copy:
        raise CliError(
            "--sent-folder requires --save-copy.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    require_confirmation(confirm, action="email.send")

    try:
        account = get_connection(ctx)
        message_body = HTMLBody(body) if body_type == "html" else body
        author = Mailbox(email_address=from_addr) if from_addr else None
        message_kwargs = {
            "account": account,
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
        if sent_folder:
            sent_copy_folder = resolve_mail_folder(account, _require_folder_arg(sent_folder))
            message.send(save_copy=True, copy_to_folder=sent_copy_folder)
        elif save_copy:
            message.send_and_save()
        else:
            message.send(save_copy=False)
        formatter.success(
            {
                "message": "Email sent",
                "subject": subject,
                "to": list(to_addrs),
                "saved_copy": save_copy,
                "sent_folder": sent_folder,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


def _sanitize_saved_draft_body(account, draft_id: str | None) -> tuple[bool, list[str]]:
    if not draft_id:
        return False, []
    try:
        draft_msg = account.drafts.get(id=draft_id)
        raw_body = getattr(draft_msg, "body", None)
        if raw_body and isinstance(raw_body, (str, HTMLBody)):
            cleaned, rules = sanitize_draft_html(str(raw_body))
            if rules:
                draft_msg.body = HTMLBody(cleaned)
                draft_msg.save(update_fields=["body"])
                return True, rules
    except Exception:
        pass
    return False, []


@email.command("reply")
@click.argument("message_id")
@click.option("--body", default=None, help="Reply body")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read body from file",
)
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.option("--to", "to_addrs", multiple=True, help="Override reply To recipients (not with --all)")
@click.option("--cc", "cc_addrs", multiple=True, help="Override reply CC recipients (not with --all)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="Override reply BCC recipients (not with --all)")
@click.option("--from", "from_addr", default=None, help="Sender email (author)")
@click.option("--all", "reply_all", is_flag=True, default=False, help="Reply to all")
@click.option("--draft", is_flag=True, default=False, help="Save as draft in Drafts folder instead of sending")
@click.option(
    "--no-sanitize",
    is_flag=True,
    default=False,
    help="Skip HTML sanitization for Outlook compatibility",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate reply without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the reply")
@click.pass_context
def email_reply(
    ctx,
    message_id,
    body,
    body_file,
    body_type,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    from_addr,
    reply_all,
    draft,
    no_sanitize,
    dry_run,
    confirm,
):
    """Reply to an existing message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file)
    if reply_all and (to_addrs or cc_addrs or bcc_addrs):
        raise CliError(
            "Recipient overrides cannot be combined with --all.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.reply",
                "preview": {
                    "message_id": message_id,
                    "reply_all": reply_all,
                    "body_type": body_type,
                    "body_length": len(body),
                    "from": from_addr,
                    "to": list(to_addrs),
                    "cc": list(cc_addrs),
                    "bcc": list(bcc_addrs),
                    "draft": draft,
                    "requires_confirm": not draft,
                },
            }
        )
        return
    if not draft:
        require_confirmation(confirm, action="email.reply")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        reply_body = HTMLBody(body) if body_type == "html" else body
        author = Mailbox(email_address=from_addr) if from_addr else None
        reply_kwargs = {"subject": f"Re: {message.subject}", "body": reply_body}
        if author:
            reply_kwargs["author"] = author
        if not reply_all:
            if to_addrs:
                reply_kwargs["to_recipients"] = _mailboxes(to_addrs)
            if cc_addrs:
                reply_kwargs["cc_recipients"] = _mailboxes(cc_addrs)
            if bcc_addrs:
                reply_kwargs["bcc_recipients"] = _mailboxes(bcc_addrs)

        if draft:
            if reply_all:
                reply_item = message.create_reply_all(**reply_kwargs)
            else:
                reply_item = message.create_reply(**reply_kwargs)
            saved_item = reply_item.save(folder=account.drafts)
            draft_id = getattr(saved_item, "id", None)
            sanitized = False
            sanitized_rules = []
            if not no_sanitize and draft_id:
                sanitized, sanitized_rules = _sanitize_saved_draft_body(account, draft_id)
            result_payload = {
                "message": "Reply draft created",
                "id": draft_id,
                "original_id": message_id,
                "subject": f"Re: {message.subject}",
                "sanitized": sanitized,
                "outcome": "succeeded",
            }
            if sanitized_rules:
                result_payload["sanitized_rules"] = sanitized_rules
            formatter.success(result_payload)
        else:
            if reply_all:
                message.reply_all(**reply_kwargs)
            else:
                message.reply(**reply_kwargs)
            formatter.success({"message": "Reply sent", "original_id": message_id, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("forward")
@click.argument("message_id")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Forward to email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="Forward CC email(s)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="Forward BCC email(s)")
@click.option("--body", default=None, help="Additional message")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read body from file",
)
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.option("--draft", is_flag=True, default=False, help="Save as draft in Drafts folder instead of sending")
@click.option(
    "--no-sanitize",
    is_flag=True,
    default=False,
    help="Skip HTML sanitization for Outlook compatibility",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate forward without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm forwarding the email")
@click.pass_context
def email_forward(
    ctx,
    message_id,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    body,
    body_file,
    body_type,
    draft,
    no_sanitize,
    dry_run,
    confirm,
):
    """Forward an existing message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file, required=False) or ""
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.forward",
                "preview": {
                    "message_id": message_id,
                    "to": list(to_addrs),
                    "cc": list(cc_addrs),
                    "bcc": list(bcc_addrs),
                    "body_type": body_type,
                    "body_length": len(body),
                    "draft": draft,
                    "requires_confirm": not draft,
                },
            }
        )
        return
    if not draft:
        require_confirmation(confirm, action="email.forward")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        forward_body = HTMLBody(body) if body_type == "html" else body
        to_recipients = _mailboxes(to_addrs)
        forward_kwargs = {
            "subject": f"Fwd: {message.subject}",
            "body": forward_body,
            "to_recipients": to_recipients,
        }
        if cc_addrs:
            forward_kwargs["cc_recipients"] = _mailboxes(cc_addrs)
        if bcc_addrs:
            forward_kwargs["bcc_recipients"] = _mailboxes(bcc_addrs)
        if draft:
            forward_item = message.create_forward(**forward_kwargs)
            saved_item = forward_item.save(folder=account.drafts)
            draft_id = getattr(saved_item, "id", None)
            sanitized = False
            sanitized_rules = []
            if not no_sanitize and draft_id:
                sanitized, sanitized_rules = _sanitize_saved_draft_body(account, draft_id)
            result_payload = {
                "message": "Forward draft created",
                "id": draft_id,
                "original_id": message_id,
                "to": list(to_addrs),
                "subject": f"Fwd: {message.subject}",
                "sanitized": sanitized,
                "outcome": "succeeded",
            }
            if sanitized_rules:
                result_payload["sanitized_rules"] = sanitized_rules
            formatter.success(result_payload)
        else:
            message.forward(**forward_kwargs)
            formatter.success(
                {"message": "Email forwarded", "original_id": message_id, "to": list(to_addrs), "outcome": "succeeded"}
            )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("search")
@click.argument("query")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    help="Well-known name, folder path, or folder id",
)
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Max results")
@click.option("--start", default=None, help="Start date/time (YYYY-MM-DD or RFC 3339)")
@click.option("--end", default=None, help="End date/time (YYYY-MM-DD or RFC 3339)")
@click.option("--from", "from_addr", default=None, help="Filter by sender (name or email; resolved via directory)")
@click.option("--has-attachments", is_flag=True, default=False, help="Only return emails with attachments")
@click.option(
    "--with-preview",
    is_flag=True,
    default=False,
    help="Include body_preview (slower for large result sets)",
)
@click.pass_context
def email_search(ctx, query, folder_name, limit, start, end, from_addr, has_attachments, with_preview):
    """Search messages with server-side filters."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        start_dt = _parse_search_date(start, is_end=False) if start else None
        end_dt = _parse_search_date(end, is_end=True) if end else None
        if start_dt and end_dt:
            ensure_start_before_end(start_dt, end_dt, action="email.search")
        folder_name = _require_folder_arg(folder_name)
        account = get_connection(ctx)
        folder = resolve_mail_folder(account, folder_name)
        criteria = Q(subject__icontains=query) | Q(body__icontains=query)
        if start_dt:
            criteria &= Q(datetime_received__gte=start_dt)
        if end_dt:
            criteria &= Q(datetime_received__lte=end_dt)
        from_resolved = None
        if from_addr is not None:
            from_addr_clean = from_addr.strip()
            if not from_addr_clean:
                raise CliError("From address cannot be empty.", code="INVALID_INPUT", exit_code=2)
            from_q = Q(sender__icontains=from_addr_clean) | Q(author__icontains=from_addr_clean)
            if "@" in from_addr_clean:
                from_resolved = True
            else:
                from_resolved = False
                try:
                    from ..core.contact_service import resolve_directory

                    resolved_entries = []
                    entries, _ = resolve_directory(account, from_addr_clean, limit=10)
                    resolved_entries.extend(entries)

                    if " " in from_addr_clean:
                        collapsed = from_addr_clean.replace(" ", "")
                        if collapsed:
                            more, _ = resolve_directory(account, collapsed, limit=10)
                            for e in more:
                                if e not in resolved_entries:
                                    resolved_entries.append(e)

                    if resolved_entries:
                        from_resolved = True
                        for entry in resolved_entries:
                            email_addr = entry.get("email")
                            if email_addr and email_addr.lower() != from_addr_clean.lower():
                                from_q |= Q(sender__icontains=email_addr) | Q(author__icontains=email_addr)
                except Exception:
                    pass
            criteria &= from_q
        if has_attachments:
            criteria &= Q(has_attachments=True)
        queryset = folder.filter(criteria)
        projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
        page, truncated, skipped_items = scan_email_page(projected.order_by("-datetime_received"), limit)
        results = [serialize_email_summary(item, include_body_preview=with_preview) for item in page]
        formatter.success(
            results,
            count=len(results),
            truncated=truncated,
            skipped_items=skipped_items,
            from_resolved=from_resolved,
        )
    except Exception as exc:
        raise classify_exception(exc) from exc


@email.command("update")
@click.argument("message_id")
@click.option("--subject", default=None, help="Replacement subject")
@click.option("--body", default=None, help="Replacement message body")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read replacement body from file",
)
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Replacement body type")
@click.option("--to", "to_addrs", multiple=True, help="Replace To recipients (drafts only)")
@click.option("--cc", "cc_addrs", multiple=True, help="Replace CC recipients (drafts only)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="Replace BCC recipients (drafts only)")
@click.option("--reply-to", "reply_to_addrs", multiple=True, help="Replace Reply-To recipients (drafts only)")
@click.option("--clear-to", is_flag=True, default=False, help="Clear To recipients (drafts only)")
@click.option("--clear-cc", is_flag=True, default=False, help="Clear CC recipients (drafts only)")
@click.option("--clear-bcc", is_flag=True, default=False, help="Clear BCC recipients (drafts only)")
@click.option("--clear-reply-to", is_flag=True, default=False, help="Clear Reply-To recipients (drafts only)")
@click.option("--from", "from_addr", default=None, help="Replacement author / Send-As identity (drafts only)")
@click.option("--category", "categories", multiple=True, help="Replace categories")
@click.option("--clear-categories", is_flag=True, default=False, help="Clear all categories")
@click.option(
    "--importance",
    type=click.Choice(tuple(IMPORTANCE_VALUES), case_sensitive=False),
    default=None,
    help="Replacement importance",
)
@click.option(
    "--sensitivity",
    type=click.Choice(tuple(SENSITIVITY_VALUES), case_sensitive=False),
    default=None,
    help="Replacement sensitivity",
)
@click.option("--read/--unread", "is_read", default=None, help="Set the read state")
@click.option(
    "--read-receipt/--no-read-receipt",
    "read_receipt_requested",
    default=None,
    help="Request or disable a read receipt (drafts only)",
)
@click.option(
    "--delivery-receipt/--no-delivery-receipt",
    "delivery_receipt_requested",
    default=None,
    help="Request or disable a delivery receipt (drafts only)",
)
@click.option(
    "--response-requested/--no-response-requested",
    "response_requested",
    default=None,
    help="Request or disable a response (drafts only)",
)
@click.option("--if-changekey", default=None, help="Only update the version returned by email read")
@click.option(
    "--conflict-resolution",
    type=click.Choice(tuple(CONFLICT_RESOLUTION_VALUES), case_sensitive=False),
    default="auto-resolve",
    show_default=True,
    help="EWS conflict behavior; --if-changekey forces never-overwrite",
)
@click.option(
    "--no-sanitize",
    is_flag=True,
    default=False,
    help="Skip HTML sanitization for Outlook compatibility",
)
@click.option("--dry-run", is_flag=True, default=False, help="Validate the requested update without changing Exchange")
@click.pass_context
def email_update(
    ctx,
    message_id,
    subject,
    body,
    body_file,
    body_type,
    to_addrs,
    cc_addrs,
    bcc_addrs,
    reply_to_addrs,
    clear_to,
    clear_cc,
    clear_bcc,
    clear_reply_to,
    from_addr,
    categories,
    clear_categories,
    importance,
    sensitivity,
    is_read,
    read_receipt_requested,
    delivery_receipt_requested,
    response_requested,
    if_changekey,
    conflict_resolution,
    no_sanitize,
    dry_run,
):
    """Update message metadata or a saved draft without sending it."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    values = _build_message_update_values(
        subject=subject,
        body=body,
        body_file=body_file,
        body_type=body_type,
        to_addrs=to_addrs,
        cc_addrs=cc_addrs,
        bcc_addrs=bcc_addrs,
        reply_to_addrs=reply_to_addrs,
        clear_to=clear_to,
        clear_cc=clear_cc,
        clear_bcc=clear_bcc,
        clear_reply_to=clear_reply_to,
        from_addr=from_addr,
        categories=categories,
        clear_categories=clear_categories,
        importance=importance,
        sensitivity=sensitivity,
        is_read=is_read,
        read_receipt_requested=read_receipt_requested,
        delivery_receipt_requested=delivery_receipt_requested,
        response_requested=response_requested,
        no_sanitize=no_sanitize,
    )
    if not values:
        raise CliError("At least one update option is required.", code="INVALID_INPUT", exit_code=2)
    if if_changekey is not None and not if_changekey.strip():
        raise CliError("--if-changekey cannot be empty.", code="INVALID_INPUT", exit_code=2)
    if if_changekey is not None and conflict_resolution.lower() == "always-overwrite":
        raise CliError(
            "--if-changekey cannot be used with --conflict-resolution always-overwrite.",
            code="INVALID_INPUT",
            exit_code=2,
        )

    is_draft_command = bool(ctx.parent and ctx.parent.info_name == "draft")
    action_name = "draft.update" if is_draft_command else "email.update"
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": action_name,
                "preview": {
                    "message_id": message_id,
                    "updated_fields": list(values),
                    "if_changekey": if_changekey,
                    "conflict_resolution": "never-overwrite" if if_changekey else conflict_resolution.lower(),
                    "requires_confirm": False,
                },
            }
        )
        return

    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        if is_draft_command and not bool(getattr(message, "is_draft", False)):
            raise CliError(
                f"Draft not found: {message_id}",
                code="NOT_FOUND",
            )
        effective_conflict_resolution = "NeverOverwrite" if if_changekey else CONFLICT_RESOLUTION_VALUES[
            conflict_resolution.lower()
        ]
        changed_fields = update_message(
            message,
            values=values,
            draft_only_fields=DRAFT_ONLY_UPDATE_FIELDS,
            expected_changekey=if_changekey,
            conflict_resolution=effective_conflict_resolution,
        )
        formatter.success(
            {
                "message": "Draft updated" if is_draft_command else "Email updated",
                "id": getattr(message, "id", message_id),
                "changekey": getattr(message, "changekey", None),
                "updated_fields": changed_fields,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("copy")
@click.argument("message_id")
@click.option("--folder", "folder_name", required=True, help="Destination well-known name, path, or folder id")
@click.option("--dry-run", is_flag=True, default=False, help="Preview the copy without changing Exchange")
@click.pass_context
def email_copy(ctx, message_id, folder_name, dry_run):
    """Copy a message into another primary-mailbox folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_name = _require_folder_arg(folder_name)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.copy",
                "preview": {"message_id": message_id, "folder": folder_name, "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        folder, copied = copy_message(message, account, folder_name)
        formatter.success(
            {
                "message": "Email copied",
                "id": message_id,
                "folder": getattr(folder, "name", folder_name),
                "copied_item": _serialize_copy_result(copied),
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("archive")
@click.argument("message_id")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    show_default=True,
    help="Destination folder inside the online archive mailbox",
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview the archive without changing Exchange")
@click.pass_context
def email_archive(ctx, message_id, folder_name, dry_run):
    """Move a message to the online archive mailbox."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_name = _require_folder_arg(folder_name)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.archive",
                "preview": {"message_id": message_id, "archive_folder": folder_name, "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        folder, archived = archive_message(message, account, folder_name)
        formatter.success(
            {
                "message": "Email archived",
                "id": message_id,
                "folder": getattr(folder, "name", folder_name),
                "archive_result": archived,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


def _change_junk_state(ctx, message_id, *, is_junk, move_item, dry_run, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    action_name = "email.mark-junk" if is_junk else "email.mark-not-junk"
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": action_name,
                "preview": {
                    "message_id": message_id,
                    "is_junk": is_junk,
                    "move_item": move_item,
                    "changes_blocked_sender_list": True,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action=action_name)
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        set_message_junk_state(message, is_junk=is_junk, move_item=move_item)
        formatter.success(
            {
                "message": "Email marked as junk" if is_junk else "Email marked as not junk",
                "id": getattr(message, "id", message_id),
                "changekey": getattr(message, "changekey", None),
                "is_junk": is_junk,
                "moved": move_item,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("mark-junk")
@click.argument("message_id")
@click.option("--move/--no-move", "move_item", default=True, help="Move the item to the Junk Email folder")
@click.option("--dry-run", is_flag=True, default=False, help="Preview without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm updating the blocked sender list")
@click.pass_context
def email_mark_junk(ctx, message_id, move_item, dry_run, confirm):
    """Mark an email as junk and block its sender."""
    _change_junk_state(ctx, message_id, is_junk=True, move_item=move_item, dry_run=dry_run, confirm=confirm)


@email.command("mark-not-junk")
@click.argument("message_id")
@click.option("--move/--no-move", "move_item", default=True, help="Move the item to the Inbox folder")
@click.option("--dry-run", is_flag=True, default=False, help="Preview without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm updating the blocked sender list")
@click.pass_context
def email_mark_not_junk(ctx, message_id, move_item, dry_run, confirm):
    """Mark an email as not junk and unblock its sender."""
    _change_junk_state(ctx, message_id, is_junk=False, move_item=move_item, dry_run=dry_run, confirm=confirm)


@email.command("restore")
@click.argument("message_id")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    show_default=True,
    help="Destination well-known name, path, or folder id",
)
@click.option("--dry-run", is_flag=True, default=False, help="Preview the restore without changing Exchange")
@click.pass_context
def email_restore(ctx, message_id, folder_name, dry_run):
    """Move a recovered or deleted email back into a primary-mailbox folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_name = _require_folder_arg(folder_name)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.restore",
                "preview": {"message_id": message_id, "folder": folder_name, "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        folder = move_message(message, account, folder_name)
        formatter.success(
            {
                "message": "Email restored",
                "source_id": message_id,
                "id": getattr(message, "id", None),
                "changekey": getattr(message, "changekey", None),
                "folder": getattr(folder, "name", folder_name),
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("mark-read")
@click.argument("message_id")
@click.pass_context
def email_mark_read(ctx, message_id):
    """Mark a message as read."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        set_message_read_state(message, is_read=True)
        formatter.success({"message": "Marked as read", "id": message_id, "is_read": True, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("mark-unread")
@click.argument("message_id")
@click.pass_context
def email_mark_unread(ctx, message_id):
    """Mark a message as unread."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        set_message_read_state(message, is_read=False)
        formatter.success({"message": "Marked as unread", "id": message_id, "is_read": False, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("move")
@click.argument("message_id")
@click.option("--folder", "folder_name", required=True, help="Destination well-known name, path, or folder id")
@click.pass_context
def email_move(ctx, message_id, folder_name):
    """Move a message to another folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_name = _require_folder_arg(folder_name)
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        folder = move_message(message, account, folder_name)
        formatter.success(
            {
                "message": "Email moved",
                "id": message_id,
                "folder": getattr(folder, "name", folder_name),
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("delete")
@click.argument("message_id")
@click.option("--permanent", is_flag=True, default=False, help="Hard-delete instead of moving to trash")
@click.option(
    "--soft",
    is_flag=True,
    default=False,
    help="Soft-delete into Recoverable Items instead of moving to trash",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate deletion without connecting or deleting")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def email_delete(ctx, message_id, permanent, soft, dry_run, confirm):
    """Move to trash, soft-delete, or hard-delete a message."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if permanent and soft:
        raise CliError(
            "Choose either --permanent or --soft, not both.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    delete_type = "hard" if permanent else ("soft" if soft else "trash")
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.delete",
                "preview": {
                    "message_id": message_id,
                    "permanent": permanent,
                    "soft": soft,
                    "delete_type": delete_type,
                    "target": "permanent deletion" if permanent else ("Recoverable Items" if soft else "move to trash"),
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="email.delete")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        action = delete_message(message, permanent=permanent, soft=soft)
        formatter.success(
            {
                "message": "Email deleted" if permanent else ("Email soft-deleted" if soft else "Email moved to trash"),
                "id": message_id,
                "permanent": permanent,
                "soft": soft,
                "action": action,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("watch")
@click.option(
    "--folder",
    "folder_name",
    default="inbox",
    help="Well-known folder name to watch",
)
@click.option(
    "--backfill-minutes",
    default=10,
    type=click.IntRange(1, MAX_BACKFILL_MINUTES),
    show_default=True,
    help="Backfill window after streaming reconnect",
)
@click.option(
    "--duration",
    "duration_seconds",
    default=None,
    type=click.IntRange(1, MAX_WATCH_DURATION_SECONDS),
    help="Stop after this many seconds",
)
@click.option(
    "--forever",
    is_flag=True,
    default=False,
    help="Run indefinitely until interrupted (human interactive only)",
)
@click.option(
    "--max-events",
    default=None,
    type=click.IntRange(1, MAX_WATCH_EVENTS),
    help="Stop after this many mail events",
)
@click.pass_context
def email_watch(ctx, folder_name, backfill_minutes, duration_seconds, forever, max_events):
    """Stream folder changes in the foreground."""
    folder_name = _require_folder_arg(folder_name)
    if duration_seconds is None and not forever:
        raise CliError(
            "email watch requires either '--duration <seconds>' or '--forever' to prevent hanging agent sessions.",
            code="WATCH_DURATION_REQUIRED",
            exit_code=2,
            retryable=False,
        )
    click.echo(f"Watching folder '{folder_name}'. Press Ctrl+C to stop.", err=True)
    original_sigterm = None
    try:

        def _sigterm_handler(signum, frame):
            raise KeyboardInterrupt()

        original_sigterm = signal.signal(signal.SIGTERM, _sigterm_handler)
    except (ValueError, AttributeError):
        pass

    try:
        for event in foreground_watch_events(
            ctx.obj.get("config_path"),
            ctx.obj.get("account_email"),
            folder_name,
            backfill_minutes,
            duration_seconds=duration_seconds,
            max_events=max_events,
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
    finally:
        if original_sigterm is not None:
            try:
                signal.signal(signal.SIGTERM, original_sigterm)
            except (ValueError, AttributeError):
                pass
