"""exchange-cli schema — machine-readable command contract."""

from __future__ import annotations

import click

from ..core.errors import CliError
from ..core.output import OutputFormatter

SCHEMA_VERSION = 1

COMMANDS = [
    {
        "name": "email.list",
        "write": False,
        "confirm": False,
        "summary": "List messages from a well-known folder, path, or folder id.",
    },
    {
        "name": "email.read",
        "write": False,
        "confirm": False,
        "summary": "Read one message. Use --fields to omit raw HTML.",
    },
    {
        "name": "email.send",
        "write": True,
        "confirm": True,
        "summary": "Send a new email. Timeouts return WRITE_OUTCOME_UNKNOWN; do not retry automatically.",
    },
    {
        "name": "email.reply",
        "write": True,
        "confirm": True,
        "summary": "Reply to a message.",
    },
    {
        "name": "email.forward",
        "write": True,
        "confirm": True,
        "summary": "Forward a message.",
    },
    {
        "name": "email.search",
        "write": False,
        "confirm": False,
        "summary": "Search a folder by subject/body and optional date range.",
    },
    {
        "name": "email.mark-read",
        "write": True,
        "confirm": False,
        "summary": "Mark a message as read.",
    },
    {
        "name": "email.mark-unread",
        "write": True,
        "confirm": False,
        "summary": "Mark a message as unread.",
    },
    {
        "name": "email.move",
        "write": True,
        "confirm": False,
        "summary": "Move a message to another folder.",
    },
    {
        "name": "email.delete",
        "write": True,
        "confirm": True,
        "summary": "Move a message to trash, or permanently delete with --permanent.",
    },
    {
        "name": "email.watch",
        "write": False,
        "confirm": False,
        "summary": "Foreground streaming watch. New-mail events include item ids only.",
    },
    {
        "name": "draft.list",
        "write": False,
        "confirm": False,
        "summary": "List drafts.",
    },
    {
        "name": "draft.create",
        "write": True,
        "confirm": False,
        "summary": "Create a draft.",
    },
    {
        "name": "draft.send",
        "write": True,
        "confirm": True,
        "summary": "Send an existing draft.",
    },
    {
        "name": "draft.delete",
        "write": True,
        "confirm": True,
        "summary": "Permanently delete a draft.",
    },
    {
        "name": "calendar.list",
        "write": False,
        "confirm": False,
        "summary": "List calendar events in a local-time range with --limit.",
    },
    {
        "name": "calendar.create",
        "write": True,
        "confirm": True,
        "summary": "Create an event. Attendee invitations require --confirm unless --notify none.",
    },
    {
        "name": "calendar.update",
        "write": True,
        "confirm": False,
        "summary": "Update an event. --notify all requires --confirm and sends update notices.",
    },
    {
        "name": "calendar.delete",
        "write": True,
        "confirm": True,
        "summary": "Delete an event. --notify all sends cancellation notices.",
    },
    {
        "name": "task.list",
        "write": False,
        "confirm": False,
        "summary": "List tasks. --status is filtered client-side because EWS cannot filter on status.",
    },
    {
        "name": "task.create",
        "write": True,
        "confirm": False,
        "summary": "Create a task.",
    },
    {
        "name": "task.update",
        "write": True,
        "confirm": False,
        "summary": "Update a task.",
    },
    {
        "name": "task.complete",
        "write": True,
        "confirm": False,
        "summary": "Mark a task completed.",
    },
    {
        "name": "task.delete",
        "write": True,
        "confirm": True,
        "summary": "Permanently delete a task.",
    },
    {
        "name": "contact.list",
        "write": False,
        "confirm": False,
        "summary": "List personal contacts.",
    },
    {
        "name": "contact.search",
        "write": False,
        "confirm": False,
        "summary": "Search personal contacts.",
    },
    {
        "name": "contact.resolve",
        "write": False,
        "confirm": False,
        "summary": "Resolve a name against the company directory / GAL.",
    },
    {
        "name": "folder.list",
        "write": False,
        "confirm": False,
        "summary": "List top-level mail folders.",
    },
    {
        "name": "folder.tree",
        "write": False,
        "confirm": False,
        "summary": "List the mail folder tree.",
    },
    {
        "name": "config.init",
        "write": False,
        "confirm": False,
        "summary": "Interactive local configuration. Password must be entered by the user.",
    },
    {
        "name": "config.show",
        "write": False,
        "confirm": False,
        "summary": "Show masked configuration.",
    },
    {
        "name": "doctor",
        "write": False,
        "confirm": False,
        "summary": "Diagnose configuration, TLS, and EWS connectivity.",
    },
]


@click.command("schema")
@click.argument("command_name", required=False)
@click.pass_context
def schema(ctx, command_name):
    """Print the machine-readable command contract."""

    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    if command_name is None:
        formatter.success({"schema_version": SCHEMA_VERSION, "commands": COMMANDS}, count=len(COMMANDS))
        return
    match = next((item for item in COMMANDS if item["name"] == command_name), None)
    if match is None:
        raise CliError(f"Unknown command: {command_name}", code="NOT_FOUND")
    formatter.success({"schema_version": SCHEMA_VERSION, **match})
