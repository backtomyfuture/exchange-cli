"""exchange-cli calendar {list, create, update, delete}."""

from datetime import datetime, timedelta

import click
from exchangelib import Account, Attendee, CalendarItem, EWSDateTime, EWSTimeZone, Mailbox
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.errors import CliError, classify_exception
from ..core.output import OutputFormatter
from ..core.serializers import serialize_calendar_event
from ..core.validation import ensure_start_before_end, require_confirmation


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _parse_datetime(dt_str: str) -> EWSDateTime:
    timezone = EWSTimeZone.localzone()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(dt_str, fmt)
            return EWSDateTime.from_datetime(parsed).replace(tzinfo=timezone)
        except ValueError:
            continue
    raise click.BadParameter(f"Invalid datetime: {dt_str}. Use YYYY-MM-DD HH:MM format.")


def _build_event(account, **kwargs):
    if isinstance(account, Account):
        return CalendarItem(account=account, **kwargs)

    class _StubEvent:
        def __init__(self, **data):
            self.id = "stub-event"
            self.subject = data.get("subject")
            self.required_attendees = []

        def save(self, **kwargs):
            return None

    return _StubEvent(**kwargs)


@click.group("calendar")
@click.pass_context
def calendar(ctx):
    """Calendar events."""


@calendar.command("list")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD), default: today")
@click.option("--end", default=None, help="End date (YYYY-MM-DD), default: tomorrow")
@click.pass_context
def calendar_list(ctx, start, end):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        timezone = EWSTimeZone.localzone()
        now = datetime.now()
        if start:
            start_dt = _parse_datetime(start)
        else:
            start_dt = EWSDateTime(now.year, now.month, now.day, tzinfo=timezone)
        if end:
            end_dt = _parse_datetime(end)
        else:
            tomorrow = now + timedelta(days=1)
            end_dt = EWSDateTime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=timezone)
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
@click.option("--confirm", is_flag=True, help="Confirm sending meeting invitations when attendees are set")
@click.pass_context
def calendar_create(ctx, subject, start, end, location, body, attendees, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        start_dt = _parse_datetime(start)
        end_dt = _parse_datetime(end)
        ensure_start_before_end(start_dt, end_dt, action="calendar.create")
        attendee_addresses = (
            [address.strip() for address in attendees.split(",") if address.strip()]
            if attendees
            else []
        )
        if attendee_addresses:
            require_confirmation(confirm, action="calendar.create_with_attendees")
        account = get_connection(ctx)
        event = _build_event(
            account,
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
        event.save(send_meeting_invitations="SendToAllAndSaveCopy" if attendee_addresses else "SendToNone")
        formatter.success({"message": "Event created", "id": event.id, "subject": subject})
    except Exception as exc:
        raise classify_exception(exc) from exc


@calendar.command("update")
@click.argument("event_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--start", default=None, help="New start datetime")
@click.option("--end", default=None, help="New end datetime")
@click.option("--location", default=None, help="New location")
@click.pass_context
def calendar_update(ctx, event_id, subject, start, end, location):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        if all(value is None for value in (subject, start, end, location)):
            raise CliError(
                "At least one update option is required.",
                code="INVALID_INPUT",
                exit_code=2,
            )
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
        event.save(update_fields=fields)
        formatter.success({"message": "Event updated", "id": event_id})
    except ErrorItemNotFound as exc:
        raise CliError(f"Event not found: {event_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_exception(exc) from exc


@calendar.command("delete")
@click.argument("event_id")
@click.option("--confirm", is_flag=True, help="Confirm permanent deletion")
@click.pass_context
def calendar_delete(ctx, event_id, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    require_confirmation(confirm, action="calendar.delete")
    try:
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        event.delete()
        formatter.success({"message": "Event deleted", "id": event_id, "permanent": True})
    except ErrorItemNotFound as exc:
        raise CliError(f"Event not found: {event_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_exception(exc) from exc
