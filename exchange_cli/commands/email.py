"""exchange-cli email {list, read, send, reply, forward, search, mark-read, move, delete, watch}."""

import json
import signal
from datetime import datetime, timezone
from pathlib import Path

import click
from exchangelib import EWSDateTime, EWSTimeZone, FileAttachment, HTMLBody, Mailbox, Message, Q

from ..core.cli import get_account
from ..core.email_service import (
    delete_message,
    find_message,
    list_email_summaries,
    move_message,
    project_email_summary_fields,
    require_message,
    resolve_mail_folder,
    scan_email_page,
    set_message_read_state,
)
from ..core.errors import CliError, classify_exception, classify_write_exception
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
    if not isinstance(folder_name, str) or not folder_name.strip():
        raise CliError("Folder is required.", code="INVALID_FOLDER", exit_code=2)
    return folder_name.strip()


def _attach_files(message, attachments) -> None:
    for path in attachments:
        with open(path, "rb") as handle:
            content = handle.read()
        message.attach(FileAttachment(name=path.name, content=content))


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
@click.option("--dry-run", is_flag=True, default=False, help="Simulate email sending without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the email")
@click.pass_context
def email_send(ctx, to_addrs, cc_addrs, bcc_addrs, subject, body, body_file, body_type, attachments, dry_run, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file)
    if dry_run:
        attachment_previews = [
            {"name": p.name, "size": p.stat().st_size if p.is_file() else None}
            for p in attachments
        ]
        formatter.success(
            {
                "dry_run": True,
                "action": "email.send",
                "preview": {
                    "to": list(to_addrs),
                    "cc": list(cc_addrs),
                    "bcc": list(bcc_addrs),
                    "subject": subject,
                    "body_type": body_type,
                    "body_length": len(body),
                    "attachments": attachment_previews,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="email.send")

    try:
        account = get_connection(ctx)
        message_body = HTMLBody(body) if body_type == "html" else body
        message = Message(
            account=account,
            subject=subject,
            body=message_body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
            cc_recipients=[Mailbox(email_address=addr) for addr in cc_addrs],
            bcc_recipients=[Mailbox(email_address=addr) for addr in bcc_addrs],
        )
        _attach_files(message, attachments)
        message.send_and_save()
        formatter.success({"message": "Email sent", "subject": subject, "to": list(to_addrs), "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("reply")
@click.argument("message_id")
@click.option("--body", default=None, help="Reply body")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read body from file",
)
@click.option("--all", "reply_all", is_flag=True, default=False, help="Reply to all")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate reply without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm sending the reply")
@click.pass_context
def email_reply(ctx, message_id, body, body_file, reply_all, dry_run, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    body = resolve_body(body, body_file)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.reply",
                "preview": {
                    "message_id": message_id,
                    "reply_all": reply_all,
                    "body_length": len(body),
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="email.reply")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        if reply_all:
            message.reply_all(subject=f"Re: {message.subject}", body=body)
        else:
            message.reply(subject=f"Re: {message.subject}", body=body)
        formatter.success({"message": "Reply sent", "original_id": message_id, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@email.command("forward")
@click.argument("message_id")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Forward to email(s)")
@click.option("--body", default=None, help="Additional message")
@click.option(
    "--body-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True, path_type=Path),
    help="Read body from file",
)
@click.option("--dry-run", is_flag=True, default=False, help="Simulate forward without connecting or sending")
@click.option("--confirm", is_flag=True, help="Confirm forwarding the email")
@click.pass_context
def email_forward(ctx, message_id, to_addrs, body, body_file, dry_run, confirm):
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
                    "body_length": len(body),
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="email.forward")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        message.forward(
            subject=f"Fwd: {message.subject}",
            body=body,
            to_recipients=[Mailbox(email_address=addr) for addr in to_addrs],
        )
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


@email.command("mark-read")
@click.argument("message_id")
@click.pass_context
def email_mark_read(ctx, message_id):
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
@click.option("--permanent", is_flag=True, default=False, help="Permanently delete instead of moving to trash")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate deletion without connecting or deleting")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def email_delete(ctx, message_id, permanent, dry_run, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "email.delete",
                "preview": {
                    "message_id": message_id,
                    "permanent": permanent,
                    "target": "permanent deletion" if permanent else "move to trash",
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="email.delete")
    try:
        account = get_connection(ctx)
        message = require_message(account, message_id)
        action = delete_message(message, permanent=permanent)
        formatter.success(
            {
                "message": "Email deleted" if permanent else "Email moved to trash",
                "id": message_id,
                "permanent": permanent,
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
    folder_name = _require_folder_arg(folder_name)
    if duration_seconds is None and not forever:
        raise CliError(
            "email watch requires either '--duration <seconds>' or '--forever' to prevent hanging agent sessions.",
            code="WATCH_DURATION_REQUIRED",
            exit_code=2,
            retryable=False,
        )
    account = get_account(ctx)
    resolve_mail_folder(account, folder_name)
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
