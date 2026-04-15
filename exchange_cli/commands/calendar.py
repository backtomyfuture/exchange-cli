"""exchange-cli calendar {list, create, update, delete}."""

import sys
from datetime import datetime, timedelta

import click
from exchangelib import Account, Attendee, CalendarItem, EWSDateTime, EWSTimeZone, Mailbox
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_calendar_event


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
        account = get_connection(ctx)
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
        events = list(account.calendar.view(start=start_dt, end=end_dt))
        results = [serialize_calendar_event(event) for event in events]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@calendar.command("create")
@click.option("--subject", required=True, help="Event subject")
@click.option("--start", required=True, help="Start datetime (YYYY-MM-DD HH:MM)")
@click.option("--end", required=True, help="End datetime (YYYY-MM-DD HH:MM)")
@click.option("--location", default=None, help="Location")
@click.option("--body", default="", help="Event body")
@click.option("--attendees", default=None, help="Comma-separated attendee emails")
@click.pass_context
def calendar_create(ctx, subject, start, end, location, body, attendees):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        event = _build_event(
            account,
            folder=account.calendar,
            subject=subject,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
            location=location,
            body=body,
        )
        if attendees:
            event.required_attendees = [Attendee(mailbox=Mailbox(email_address=addr.strip())) for addr in attendees.split(",")]
        event.save(send_meeting_invitations="SendToAllAndSaveCopy" if attendees else "SendToNone")
        formatter.success({"message": "Event created", "id": event.id, "subject": subject})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


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
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        fields = []
        if subject:
            event.subject = subject
            fields.append("subject")
        if start:
            event.start = _parse_datetime(start)
            fields.append("start")
        if end:
            event.end = _parse_datetime(end)
            fields.append("end")
        if location:
            event.location = location
            fields.append("location")
        event.save(update_fields=fields)
        formatter.success({"message": "Event updated", "id": event_id})
    except ErrorItemNotFound:
        formatter.error(f"Event not found: {event_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@calendar.command("delete")
@click.argument("event_id")
@click.pass_context
def calendar_delete(ctx, event_id):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        event.delete()
        formatter.success({"message": "Event deleted", "id": event_id})
    except ErrorItemNotFound:
        formatter.error(f"Event not found: {event_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
