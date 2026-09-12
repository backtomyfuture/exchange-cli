"""exchange-cli schema — machine-readable command contract."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import click

from ..core.errors import CliError
from ..core.output import OutputFormatter

SCHEMA_VERSION = 2

COMMAND_SEMANTICS: dict[str, dict[str, Any]] = {
    # Email operations
    "email.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List messages from a well-known folder, path, or folder id.",
        "error_codes": ["INVALID_FOLDER", "CONNECTION_ERROR", "AUTH_ERROR"],
    },
    "email.read": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Read one message. Returns clean Markdown body by default; use --include-html for raw HTML.",
        "error_codes": ["NOT_FOUND", "CONNECTION_ERROR", "AUTH_ERROR"],
    },
    "email.send": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Send a new email. Timeouts return WRITE_OUTCOME_UNKNOWN; do not retry automatically.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "INVALID_INPUT"],
    },
    "email.reply": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Reply to an existing message.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "email.forward": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Forward an existing message.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "email.search": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Search a folder by subject/body and optional date range.",
        "error_codes": ["INVALID_FOLDER", "INVALID_INPUT"],
    },
    "email.mark-read": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Mark a message as read.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "email.mark-unread": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Mark a message as unread.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "email.move": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Move a message to another folder.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "NOT_FOUND", "INVALID_FOLDER"],
    },
    "email.delete": {
        "write": True,
        "confirm": True,
        "effect": "internal_modify",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Delete a message (move to trash by default, or permanent).",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "email.watch": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Stream new email events in the foreground.",
        "error_codes": ["INVALID_FOLDER", "CONNECTION_ERROR"],
    },
    # Draft management
    "draft.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List draft messages.",
        "error_codes": ["CONNECTION_ERROR", "AUTH_ERROR"],
    },
    "draft.create": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Create a new draft message.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "INVALID_INPUT"],
    },
    "draft.send": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Send an existing draft message.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "draft.delete": {
        "write": True,
        "confirm": True,
        "effect": "internal_modify",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Delete a draft message.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    # Calendar operations
    "calendar.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List calendar events in a date range.",
        "error_codes": ["INVALID_INPUT", "CONNECTION_ERROR"],
    },
    "calendar.create": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Create a new calendar event or meeting.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "INVALID_INPUT"],
    },
    "calendar.update": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Update a calendar event.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "calendar.delete": {
        "write": True,
        "confirm": True,
        "effect": "external_send",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Delete a calendar event.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    # Task operations
    "task.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List tasks with optional status filter.",
        "error_codes": ["CONNECTION_ERROR"],
    },
    "task.create": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Create a new task.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "INVALID_INPUT"],
    },
    "task.update": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Update task fields.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "task.complete": {
        "write": True,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "never_on_unknown_outcome",
        "summary": "Mark a task as completed.",
        "error_codes": ["WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    "task.delete": {
        "write": True,
        "confirm": True,
        "effect": "internal_modify",
        "confirmation": "required",
        "retry": "never_on_unknown_outcome",
        "summary": "Delete a task.",
        "error_codes": ["CONFIRMATION_REQUIRED", "WRITE_OUTCOME_UNKNOWN", "NOT_FOUND"],
    },
    # Contacts
    "contact.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List personal contacts.",
        "error_codes": ["CONNECTION_ERROR"],
    },
    "contact.search": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Search personal contacts.",
        "error_codes": ["CONNECTION_ERROR"],
    },
    "contact.resolve": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Resolve names or emails against the Global Address List (GAL).",
        "error_codes": ["CONNECTION_ERROR"],
    },
    # Folders
    "folder.list": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List top-level folders.",
        "error_codes": ["CONNECTION_ERROR"],
    },
    "folder.tree": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "List the full mail folder tree.",
        "error_codes": ["CONNECTION_ERROR"],
    },
    # Configuration and Diagnostics
    "config.init": {
        "write": False,
        "confirm": False,
        "effect": "internal_modify",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Interactive local configuration setup. Password must be entered by the user.",
        "error_codes": ["CONFIG_INVALID"],
    },
    "config.show": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Show masked configuration.",
        "error_codes": ["CONFIG_NOT_FOUND"],
    },
    "doctor": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Diagnose configuration, TLS, and EWS connectivity.",
        "error_codes": ["INSECURE_TLS", "CA_BUNDLE_NOT_FOUND", "AUTH_ERROR", "CONNECTION_ERROR"],
    },
    "schema": {
        "write": False,
        "confirm": False,
        "effect": "read",
        "confirmation": "none",
        "retry": "safe",
        "summary": "Print the machine-readable command contract with options and arguments.",
        "error_codes": ["NOT_FOUND"],
    },
}


def _introspect_param(param: click.Parameter) -> dict[str, Any]:
    is_option = isinstance(param, click.Option)
    ptype = param.type
    type_name = "string"
    extra: dict[str, Any] = {}

    if isinstance(ptype, click.Choice):
        type_name = "choice"
        extra["choices"] = list(ptype.choices)
    elif isinstance(ptype, click.IntRange):
        type_name = "integer"
        if ptype.min is not None:
            extra["min"] = ptype.min
        if ptype.max is not None:
            extra["max"] = ptype.max
    elif isinstance(ptype, click.types.IntParamType):
        type_name = "integer"
    elif isinstance(ptype, click.types.BoolParamType) or getattr(param, "is_flag", False):
        type_name = "boolean"
    elif isinstance(ptype, click.types.Path):
        type_name = "path"
    else:
        type_name = "string"

    entry: dict[str, Any] = {
        "name": param.opts[-1] if (is_option and param.opts) else param.name,
        "required": bool(param.required),
        "type": type_name,
        **extra,
    }

    if is_option:
        entry["flags"] = list(param.opts)
        entry["multiple"] = bool(param.multiple)
        entry["is_flag"] = bool(param.is_flag)
        if param.help:
            entry["help"] = param.help

        default = param.default
        has_default = (
            default is not None
            and not (hasattr(click.core, "UNSET") and default is click.core.UNSET)
            and not (param.is_flag and default is False)
            and not (isinstance(default, (list, tuple)) and len(default) == 0)
        )
        if has_default:
            entry["default"] = str(default) if isinstance(default, Path) else default

    return entry


def _introspect_command(cmd_name: str, cmd: click.Command) -> dict[str, Any]:
    semantics = COMMAND_SEMANTICS.get(cmd_name, {})
    arguments = [_introspect_param(p) for p in cmd.params if isinstance(p, click.Argument)]
    options = [_introspect_param(p) for p in cmd.params if isinstance(p, click.Option)]

    confirm = semantics.get("confirm")
    if confirm is None:
        confirm = any(opt.get("name") == "--confirm" for opt in options)

    write = semantics.get("write")
    if write is None:
        write = confirm or any(
            k in cmd_name
            for k in ("create", "delete", "update", "send", "reply", "forward", "complete", "mark-", "move")
        )

    summary = semantics.get("summary")
    if not summary:
        doc = cmd.help or cmd.short_help or ""
        summary = doc.strip().splitlines()[0] if doc else f"Execute {cmd_name}"

    effect = semantics.get("effect")
    if not effect:
        effect = "external_send" if confirm else ("internal_modify" if write else "read")

    confirmation = semantics.get("confirmation")
    if not confirmation:
        confirmation = "required" if confirm else "none"

    retry = semantics.get("retry")
    if not retry:
        retry = "never_on_unknown_outcome" if write else "safe"

    error_codes = semantics.get("error_codes", [])

    return {
        "name": cmd_name,
        "summary": summary,
        "write": write,
        "confirm": confirm,
        "effect": effect,
        "confirmation": confirmation,
        "retry": retry,
        "arguments": arguments,
        "options": options,
        "error_codes": error_codes,
    }


def get_command_catalog() -> list[dict[str, Any]]:
    """Introspect all commands registered in exchange-cli."""
    from ..main import _COMMAND_MODULES

    catalog: list[dict[str, Any]] = []
    for mod_name, mod_path in _COMMAND_MODULES.items():
        if mod_name == "schema":
            catalog.append(_introspect_command("schema", schema))
            continue
        try:
            mod = importlib.import_module(mod_path)
            obj = getattr(mod, mod_name)
            if isinstance(obj, click.Group):
                for sub_name, sub_cmd in sorted(obj.commands.items()):
                    catalog.append(_introspect_command(f"{mod_name}.{sub_name}", sub_cmd))
            elif isinstance(obj, click.Command):
                catalog.append(_introspect_command(mod_name, obj))
        except Exception:
            continue

    return sorted(catalog, key=lambda c: c["name"])


class _LazyCommandsList(list):
    """Backwards-compatible list interface that lazily loads the introspected catalog."""

    def _load(self) -> list[dict[str, Any]]:
        return get_command_catalog()

    def __iter__(self):
        return iter(self._load())

    def __len__(self):
        return len(self._load())

    def __getitem__(self, index):
        return self._load()[index]


COMMANDS = _LazyCommandsList()


@click.command("schema")
@click.argument("command_name", required=False)
@click.pass_context
def schema(ctx, command_name):
    """Print the machine-readable command contract."""

    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    catalog = get_command_catalog()
    if command_name is None:
        formatter.success({"schema_version": SCHEMA_VERSION, "commands": catalog}, count=len(catalog))
        return
    match = next((item for item in catalog if item["name"] == command_name), None)
    if match is None:
        raise CliError(f"Unknown command: {command_name}", code="NOT_FOUND", exit_code=2)
    formatter.success({"schema_version": SCHEMA_VERSION, **match})
