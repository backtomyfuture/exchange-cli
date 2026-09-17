"""Mailbox-level settings and inbox-rule conversion helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from exchangelib import EWSDateTime, Mailbox, OofSettings
from exchangelib.properties import (
    Actions,
    Conditions,
    Exceptions,
    ItemId,
    Rule,
    SendingAs,
    WithinDateRange,
    WithinSizeRange,
)
from exchangelib.services import GetMailTips

from .errors import CliError
from .io import read_text_file
from .validation import ensure_start_before_end

OOF_STATES = {
    "enabled": OofSettings.ENABLED,
    "scheduled": OofSettings.SCHEDULED,
    "disabled": OofSettings.DISABLED,
}
OOF_EXTERNAL_AUDIENCES = {
    "none": "None",
    "known": "Known",
    "all": "All",
}
MAIL_TIP_REQUESTS = (
    "All",
    "OutOfOfficeMessage",
    "MailboxFullStatus",
    "CustomMailTip",
    "ExternalMemberCount",
    "TotalMemberCount",
    "MaxMessageSize",
    "DeliveryRestriction",
    "ModerationStatus",
    "InvalidRecipient",
)

_RULE_FIELDS = {"display_name", "priority", "is_enabled", "conditions", "exceptions", "actions"}
_RULE_COMPONENT_FIELDS = {field.name for field in Conditions.FIELDS}
_RULE_ACTION_FIELDS = {field.name for field in Actions.FIELDS}
_RULE_FOLDER_ACTION_FIELDS = {"copy_to_folder", "move_to_folder"}
_IMPORTANCE_VALUES = {"low": "Low", "normal": "Normal", "high": "High"}


def _invalid_rule_spec(message: str, *, details: dict[str, Any] | None = None) -> CliError:
    return CliError(message, code="INVALID_RULE_SPEC", exit_code=2, details=details)


def _require_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid_rule_spec(f"{field} must be a JSON object.", details={"field": field})
    return value


def _normalize_rule_choice(value: Any, *, field: str, choices: dict[str, str]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _invalid_rule_spec(f"{field} must be a non-empty string.", details={"field": field})
    canonical = choices.get(value.lower())
    if canonical is None:
        raise _invalid_rule_spec(
            f"Unsupported value for {field}: {value!r}.",
            details={"field": field, "allowed": list(choices)},
        )
    return canonical


def _parse_rule_datetime(value: Any, *, field: str) -> EWSDateTime:
    if not isinstance(value, str) or not value.strip():
        raise _invalid_rule_spec(
            f"{field} must be a timezone-aware RFC 3339 timestamp.",
            details={"field": field},
        )
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid_rule_spec(
            f"{field} must be a timezone-aware RFC 3339 timestamp.",
            details={"field": field},
        ) from exc
    if parsed.tzinfo is None:
        raise _invalid_rule_spec(
            f"{field} must include a timezone offset.",
            details={"field": field},
        )
    return EWSDateTime.from_datetime(parsed.astimezone(timezone.utc))


def _normalize_date_range(value: Any, *, field: str) -> dict[str, str]:
    payload = _require_mapping(value, field=field)
    allowed = {"start_date_time", "end_date_time"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise _invalid_rule_spec(
            f"Unsupported fields in {field}: {', '.join(unknown)}.",
            details={"field": field, "allowed": sorted(allowed)},
        )
    if set(payload) != allowed:
        raise _invalid_rule_spec(
            f"{field} requires start_date_time and end_date_time.",
            details={"field": field, "required": sorted(allowed)},
        )
    start = _parse_rule_datetime(payload["start_date_time"], field=f"{field}.start_date_time")
    end = _parse_rule_datetime(payload["end_date_time"], field=f"{field}.end_date_time")
    ensure_start_before_end(start, end, action=field)
    return {
        "start_date_time": start.isoformat(),
        "end_date_time": end.isoformat(),
    }


def _normalize_size_range(value: Any, *, field: str) -> dict[str, int]:
    payload = _require_mapping(value, field=field)
    allowed = {"minimum_size", "maximum_size"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise _invalid_rule_spec(
            f"Unsupported fields in {field}: {', '.join(unknown)}.",
            details={"field": field, "allowed": sorted(allowed)},
        )
    if set(payload) != allowed:
        raise _invalid_rule_spec(
            f"{field} requires minimum_size and maximum_size.",
            details={"field": field, "required": sorted(allowed)},
        )
    minimum = payload["minimum_size"]
    maximum = payload["maximum_size"]
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or minimum < 0
        or maximum < minimum
    ):
        raise _invalid_rule_spec(
            f"{field} requires non-negative integer bounds where minimum_size is no greater than maximum_size.",
            details={"field": field},
        )
    return {"minimum_size": minimum, "maximum_size": maximum}


def _make_rule_component(component_type, value: dict[str, Any] | None):
    if value is None:
        return None
    component_values = dict(value)
    if "within_date_range" in component_values:
        component_values["within_date_range"] = WithinDateRange(
            **{
                key: _parse_rule_datetime(date_value, field=f"within_date_range.{key}")
                for key, date_value in component_values["within_date_range"].items()
            }
        )
    if "within_size_range" in component_values:
        component_values["within_size_range"] = WithinSizeRange(**component_values["within_size_range"])
    component = component_type(**component_values)
    component.clean()
    return component


def _validate_rule_component(value: Any, *, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    payload = _require_mapping(value, field=field)
    unknown = sorted(set(payload) - _RULE_COMPONENT_FIELDS)
    if unknown:
        raise _invalid_rule_spec(
            f"Unsupported fields in {field}: {', '.join(unknown)}.",
            details={"field": field, "allowed": sorted(_RULE_COMPONENT_FIELDS)},
        )
    normalized = dict(payload)
    if "within_date_range" in normalized:
        normalized["within_date_range"] = _normalize_date_range(normalized["within_date_range"], field=field)
    if "within_size_range" in normalized:
        normalized["within_size_range"] = _normalize_size_range(normalized["within_size_range"], field=field)
    try:
        _make_rule_component(Conditions if field == "conditions" else Exceptions, normalized)
    except (TypeError, ValueError) as exc:
        raise _invalid_rule_spec(str(exc) or f"Invalid {field} value.", details={"field": field}) from exc
    return normalized


def _normalize_folder_reference(value: Any, *, field: str) -> str | dict[str, str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    payload = _require_mapping(value, field=field)
    allowed = {"id", "changekey", "distinguished_id"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise _invalid_rule_spec(
            f"{field} must be a folder path string or an object with id (and optional changekey) or distinguished_id.",
            details={"field": field, "allowed": sorted(allowed)},
        )
    if "distinguished_id" in payload:
        if set(payload) != {"distinguished_id"}:
            raise _invalid_rule_spec(
                f"{field}.distinguished_id cannot be combined with an id or changekey.",
                details={"field": field},
            )
        identifier = payload["distinguished_id"]
        if not isinstance(identifier, str) or not identifier.strip():
            raise _invalid_rule_spec(
                f"{field}.distinguished_id must be a non-empty string.",
                details={"field": field},
            )
        return {"distinguished_id": identifier.strip()}
    identifier = payload.get("id")
    if not isinstance(identifier, str) or not identifier.strip():
        raise _invalid_rule_spec(
            f"{field}.id must be a non-empty folder identifier.",
            details={"field": field},
        )
    normalized = {"id": identifier.strip()}
    if "changekey" in payload:
        changekey = payload["changekey"]
        if not isinstance(changekey, str) or not changekey.strip():
            raise _invalid_rule_spec(
                f"{field}.changekey must be a non-empty string.",
                details={"field": field},
            )
        normalized["changekey"] = changekey.strip()
    return normalized


def _normalize_server_reply_reference(value: Any) -> str | dict[str, str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    payload = _require_mapping(value, field="actions.server_reply_with_message")
    unknown = sorted(set(payload) - {"id", "changekey"})
    if unknown or not isinstance(payload.get("id"), str) or not payload["id"].strip():
        raise _invalid_rule_spec(
            "actions.server_reply_with_message must be an item id string or an object with id and optional changekey.",
            details={"field": "actions.server_reply_with_message"},
        )
    normalized = {"id": payload["id"].strip()}
    if "changekey" in payload:
        if not isinstance(payload["changekey"], str) or not payload["changekey"].strip():
            raise _invalid_rule_spec(
                "actions.server_reply_with_message.changekey must be a non-empty string.",
                details={"field": "actions.server_reply_with_message.changekey"},
            )
        normalized["changekey"] = payload["changekey"].strip()
    return normalized


def _has_effective_action(actions: dict[str, Any]) -> bool:
    for value in actions.values():
        if value is None:
            continue
        if isinstance(value, bool):
            if value:
                return True
            continue
        if isinstance(value, (str, list, dict)) and not value:
            continue
        return True
    return False


def _validate_rule_actions(value: Any) -> dict[str, Any]:
    payload = _require_mapping(value, field="actions")
    unknown = sorted(set(payload) - _RULE_ACTION_FIELDS)
    if unknown:
        raise _invalid_rule_spec(
            f"Unsupported fields in actions: {', '.join(unknown)}.",
            details={"field": "actions", "allowed": sorted(_RULE_ACTION_FIELDS)},
        )
    normalized = dict(payload)
    for action_field in _RULE_FOLDER_ACTION_FIELDS & set(normalized):
        normalized[action_field] = _normalize_folder_reference(
            normalized[action_field], field=f"actions.{action_field}"
        )
    if "server_reply_with_message" in normalized:
        normalized["server_reply_with_message"] = _normalize_server_reply_reference(
            normalized["server_reply_with_message"]
        )
    if "mark_importance" in normalized:
        normalized["mark_importance"] = _normalize_rule_choice(
            normalized["mark_importance"], field="actions.mark_importance", choices=_IMPORTANCE_VALUES
        )
    if not _has_effective_action(normalized):
        raise _invalid_rule_spec("actions must contain at least one effective action.", details={"field": "actions"})

    non_folder_actions = {key: value for key, value in normalized.items() if key not in _RULE_FOLDER_ACTION_FIELDS}
    if "server_reply_with_message" in non_folder_actions:
        item_reference = non_folder_actions["server_reply_with_message"]
        non_folder_actions["server_reply_with_message"] = (
            ItemId(id=item_reference) if isinstance(item_reference, str) else ItemId(**item_reference)
        )
    try:
        Actions(**non_folder_actions).clean()
    except (TypeError, ValueError) as exc:
        raise _invalid_rule_spec(str(exc) or "Invalid actions value.", details={"field": "actions"}) from exc
    return normalized


def load_rule_spec(path: Path, *, creating: bool) -> dict[str, Any]:
    """Read a fully validated, JSON-safe inbox-rule specification."""
    try:
        value = json.loads(read_text_file(path))
    except json.JSONDecodeError as exc:
        raise _invalid_rule_spec(f"Rule spec is not valid JSON: {exc.msg}.") from exc
    payload = _require_mapping(value, field="rule spec")
    unknown = sorted(set(payload) - _RULE_FIELDS)
    if unknown:
        raise _invalid_rule_spec(
            f"Unsupported fields in rule spec: {', '.join(unknown)}.",
            details={"allowed": sorted(_RULE_FIELDS)},
        )
    if not payload:
        raise _invalid_rule_spec("Rule spec cannot be empty.")

    normalized: dict[str, Any] = {}
    if "display_name" in payload:
        display_name = payload["display_name"]
        if not isinstance(display_name, str) or not display_name.strip():
            raise _invalid_rule_spec("display_name must be a non-empty string.", details={"field": "display_name"})
        normalized["display_name"] = display_name.strip()
    if "priority" in payload:
        priority = payload["priority"]
        if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
            raise _invalid_rule_spec("priority must be a non-negative integer.", details={"field": "priority"})
        normalized["priority"] = priority
    if "is_enabled" in payload:
        if not isinstance(payload["is_enabled"], bool):
            raise _invalid_rule_spec("is_enabled must be a boolean.", details={"field": "is_enabled"})
        normalized["is_enabled"] = payload["is_enabled"]
    for component_field in ("conditions", "exceptions"):
        if component_field in payload:
            normalized[component_field] = _validate_rule_component(payload[component_field], field=component_field)
    if "actions" in payload:
        normalized["actions"] = _validate_rule_actions(payload["actions"])

    if creating:
        missing = sorted({"display_name", "priority", "actions"} - set(normalized))
        if missing:
            raise _invalid_rule_spec(
                f"Creating a rule requires: {', '.join(missing)}.",
                details={"required": ["display_name", "priority", "actions"]},
            )
        normalized.setdefault("is_enabled", True)
    return normalized


def _resolve_rule_folder(account, value: str | dict[str, str]):
    from .email_service import resolve_mail_folder

    if isinstance(value, str):
        return resolve_mail_folder(account, value)
    return resolve_mail_folder(account, value.get("id") or value["distinguished_id"])


def _build_rule_actions(account, value: dict[str, Any]) -> Actions:
    action_values = dict(value)
    for action_field in _RULE_FOLDER_ACTION_FIELDS & set(action_values):
        action_values[action_field] = _resolve_rule_folder(account, action_values[action_field])
    if "server_reply_with_message" in action_values:
        item_reference = action_values["server_reply_with_message"]
        action_values["server_reply_with_message"] = (
            ItemId(id=item_reference) if isinstance(item_reference, str) else ItemId(**item_reference)
        )
    actions = Actions(**action_values)
    actions.clean()
    return actions


def build_rule(account, spec: dict[str, Any], *, existing: Rule | None = None) -> Rule:
    """Build a new rule or patch an existing rule from a normalized spec."""
    values = dict(spec)
    if "conditions" in values:
        values["conditions"] = _make_rule_component(Conditions, values["conditions"])
    if "exceptions" in values:
        values["exceptions"] = _make_rule_component(Exceptions, values["exceptions"])
    if "actions" in values:
        values["actions"] = _build_rule_actions(account, values["actions"])

    if existing is None:
        rule = Rule(**values)
    else:
        rule = existing
        for field, value in values.items():
            setattr(rule, field, value)
    rule.clean()
    return rule


def find_rule(account, rule_id: str) -> Rule:
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise CliError("Rule id is required.", code="INVALID_INPUT", exit_code=2)
    for rule in account.rules:
        if getattr(rule, "id", None) == rule_id:
            return rule
    raise CliError(f"Inbox rule not found: {rule_id}", code="NOT_FOUND")


def delete_rule(account, rule: Rule) -> None:
    """Delete a rule, applying the upstream workaround for disabled rules."""
    if rule.is_enabled is False:
        rule.is_enabled = True
        rule.priority = 10**6
        rule.conditions = None
        rule.exceptions = None
        rule.actions = Actions(stop_processing_rules=True)
        account.set_rule(rule)
    account.delete_rule(rule)


def get_mail_tips(account, *, recipients: tuple[str, ...], sending_as: str | None, requested: str):
    """Query Exchange mail tips for one or more recipients."""
    if not recipients or any(not isinstance(address, str) or not address.strip() for address in recipients):
        raise CliError("At least one non-empty --to recipient is required.", code="INVALID_INPUT", exit_code=2)
    sender = sending_as.strip() if sending_as else account.primary_smtp_address
    if not isinstance(sender, str) or not sender.strip():
        raise CliError("A non-empty sending address is required.", code="INVALID_INPUT", exit_code=2)
    results = list(
        GetMailTips(protocol=account.protocol).call(
            sending_as=SendingAs(email_address=sender),
            recipients=[Mailbox(email_address=address.strip()) for address in recipients],
            mail_tips_requested=requested,
        )
    )
    for result in results:
        if isinstance(result, Exception):
            raise result
    return results


def build_oof_settings(
    *,
    state: str,
    external_audience: str,
    start=None,
    end=None,
    internal_reply=None,
    external_reply=None,
) -> OofSettings:
    """Validate and build an OOF value before an Account property write."""
    canonical_state = OOF_STATES[state]
    if (start is None) != (end is None):
        raise CliError(
            "--start and --end must be used together for OOF settings.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if canonical_state == OofSettings.SCHEDULED:
        if start is None:
            raise CliError(
                "Scheduled OOF requires both --start and --end.",
                code="INVALID_INPUT",
                exit_code=2,
            )
        ensure_start_before_end(start, end, action="mailbox.oof.set")
    elif start is not None:
        raise CliError(
            "--start and --end are only valid when --state scheduled.",
            code="INVALID_INPUT",
            exit_code=2,
        )

    if canonical_state == OofSettings.DISABLED:
        if internal_reply is not None or external_reply is not None:
            raise CliError(
                "Reply bodies are only valid when OOF is enabled or scheduled.",
                code="INVALID_INPUT",
                exit_code=2,
            )
    elif not internal_reply or not external_reply:
        raise CliError(
            "Enabled or scheduled OOF requires both --internal-reply and --external-reply.",
            code="INVALID_INPUT",
            exit_code=2,
        )

    settings = OofSettings(
        state=canonical_state,
        external_audience=OOF_EXTERNAL_AUDIENCES[external_audience],
        start=start,
        end=end,
        internal_reply=internal_reply,
        external_reply=external_reply,
    )
    # Run the upstream validator before displaying a dry run or connecting to
    # Exchange. It also enforces that a scheduled end is in the future.
    settings.clean()
    return settings
