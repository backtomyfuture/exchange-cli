"""exchange-cli calendar {list, create, update, delete}."""

from datetime import datetime, timedelta

import click
from exchangelib import Attendee, CalendarItem, EWSDateTime, EWSTimeZone, Mailbox
from exchangelib.errors import ErrorItemNotFound

from ..core.cli import get_account
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.output import OutputFormatter
from ..core.serializers import serialize_calendar_event
from ..core.validation import (
    MEETING_NOTIFY_CHOICES,
    MEETING_NOTIFY_MAP,
    ensure_start_before_end,
    require_confirmation,
)


def get_connection(ctx):
    return get_account(ctx)


def _parse_datetime(dt_str: str) -> EWSDateTime:
    timezone = EWSTimeZone.localzone()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(dt_str, fmt)
            return EWSDateTime.from_datetime(parsed).replace(tzinfo=timezone)
        except ValueError:
            continue
    raise click.BadParameter(f"Invalid datetime: {dt_str}. Use YYYY-MM-DD HH:MM format.")


def _parse_list_bound(value: str | None, *, is_end: bool, now: datetime, timezone: EWSTimeZone) -> EWSDateTime:
    """Parse calendar.list bounds.

    Date-only --end is inclusive of that day: EWS calendar.view uses an exclusive
    end, so YYYY-MM-DD becomes the following midnight.
    """

    if value is None:
        if is_end:
            bound = now + timedelta(days=1)
        else:
            bound = now
        return EWSDateTime(bound.year, bound.month, bound.day, tzinfo=timezone)

    for fmt, has_time in (
        ("%Y-%m-%d %H:%M:%S", True),
        ("%Y-%m-%d %H:%M", True),
        ("%Y-%m-%d", False),
    ):
        try:
            parsed = datetime.strptime(value, fmt)
            if is_end and not has_time:
                parsed = parsed + timedelta(days=1)
            return EWSDateTime.from_datetime(parsed).replace(tzinfo=timezone)
        except ValueError:
            continue
    raise click.BadParameter(f"Invalid datetime: {value}. Use YYYY-MM-DD or YYYY-MM-DD HH:MM.")


def _notify_value(notify: str) -> str:
    return MEETING_NOTIFY_MAP[notify]


@click.group("calendar")
@click.pass_context
def calendar(ctx):
    """Calendar events."""


@calendar.command("list")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD), default: today")
@click.option("--end", default=None, help="Inclusive end date (YYYY-MM-DD), default: today")
@click.pass_context
def calendar_list(ctx, start, end):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        timezone = EWSTimeZone.localzone()
        now = datetime.now()
        start_dt = _parse_list_bound(start, is_end=False, now=now, timezone=timezone)
        end_dt = _parse_list_bound(end, is_end=True, now=now, timezone=timezone)
        ensure_start_before_end(start_dt, end_dt, action="calendar.list")
        account = get_connection(ctx)
        events = list(account.calendar.view(start=start_dt, end=end_dt))
        results = [serialize_calendar_event(event) for event in events]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@calendar.command("create")
@click.option("--subject", required=True, help="Event subject")
@click.option("--start", required=True, help="Start datetime (YYYY-MM-DD HH:MM)")
@click.option("--end", required=True, help="End datetime (YYYY-MM-DD HH:MM)")
@click.option("--location", default=None, help="Location")
@click.option("--body", default="", help="Event body")
@click.option("--attendees", default=None, help="Comma-separated attendee emails")
@click.option(
    "--notify",
    default="all",
    type=click.Choice(MEETING_NOTIFY_CHOICES, case_sensitive=False),
    help="Meeting invitation behaviour when attendees are set",
)
@click.option("--confirm", is_flag=True, help="Confirm sending meeting invitations when attendees are set")
@click.pass_context
def calendar_create(ctx, subject, start, end, location, body, attendees, notify, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        start_dt = _parse_datetime(start)
        end_dt = _parse_datetime(end)
        ensure_start_before_end(start_dt, end_dt, action="calendar.create")
        attendee_addresses = (
            [address.strip() for address in attendees.split(",") if address.strip()] if attendees else []
        )
        notify = notify.lower()
        if attendee_addresses and notify != "none":
            require_confirmation(confirm, action="calendar.create_with_attendees")
        account = get_connection(ctx)
        event = CalendarItem(
            account=account,
            folder=account.calendar,
            subject=subject,
            start=start_dt,
            end=end_dt,
            location=location,
            body=body,
        )
        if attendee_addresses:
            event.required_attendees = [
                Attendee(mailbox=Mailbox(email_address=address)) for address in attendee_addresses
            ]
        send_invitations = _notify_value(notify) if attendee_addresses else "SendToNone"
        event.save(send_meeting_invitations=send_invitations)
        formatter.success(
            {
                "message": "Event created",
                "id": event.id,
                "subject": subject,
                "notified": send_invitations != "SendToNone",
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@calendar.command("update")
@click.argument("event_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--start", default=None, help="New start datetime")
@click.option("--end", default=None, help="New end datetime")
@click.option("--location", default=None, help="New location")
@click.option(
    "--notify",
    default="none",
    type=click.Choice(MEETING_NOTIFY_CHOICES, case_sensitive=False),
    help="Whether to notify attendees of the update",
)
@click.option("--confirm", is_flag=True, help="Confirm sending update notices when --notify all is set")
@click.pass_context
def calendar_update(ctx, event_id, subject, start, end, location, notify, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        if all(value is None for value in (subject, start, end, location)):
            raise CliError(
                "At least one update option is required.",
                code="INVALID_INPUT",
                exit_code=2,
            )
        notify = notify.lower()
        if notify != "none":
            require_confirmation(confirm, action="calendar.update_with_notice")
        start_dt = _parse_datetime(start) if start is not None else None
        end_dt = _parse_datetime(end) if end is not None else None
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        if start_dt is not None or end_dt is not None:
            ensure_start_before_end(
                start_dt if start_dt is not None else event.start,
                end_dt if end_dt is not None else event.end,
                action="calendar.update",
            )
        fields = []
        if subject is not None:
            event.subject = subject
            fields.append("subject")
        if start_dt is not None:
            event.start = start_dt
            fields.append("start")
        if end_dt is not None:
            event.end = end_dt
            fields.append("end")
        if location is not None:
            event.location = location
            fields.append("location")
        send_invitations = _notify_value(notify)
        event.save(update_fields=fields, send_meeting_invitations=send_invitations)
        formatter.success(
            {
                "message": "Event updated",
                "id": event_id,
                "notified": send_invitations != "SendToNone",
                "outcome": "succeeded",
            }
        )
    except ErrorItemNotFound as exc:
        raise CliError(f"Event not found: {event_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@calendar.command("delete")
@click.argument("event_id")
@click.option(
    "--notify",
    default="none",
    type=click.Choice(MEETING_NOTIFY_CHOICES, case_sensitive=False),
    help="Whether to send cancellation notices",
)
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def calendar_delete(ctx, event_id, notify, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    notify = notify.lower()
    require_confirmation(confirm, action="calendar.delete")
    if notify != "none":
        require_confirmation(confirm, action="calendar.delete_with_notice")
    try:
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        send_cancellations = _notify_value(notify)
        event.delete(send_meeting_cancellations=send_cancellations)
        formatter.success(
            {
                "message": "Event deleted",
                "id": event_id,
                "permanent": True,
                "notified": send_cancellations != "SendToNone",
                "outcome": "succeeded",
            }
        )
    except ErrorItemNotFound as exc:
        raise CliError(f"Event not found: {event_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc
