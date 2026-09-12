"""Shared input validation and safe local file operations."""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

from exchangelib import FileAttachment

from .errors import CliError

FOLDER_NAMES = ("inbox", "sent", "drafts", "trash", "junk")
MAX_RESULTS = 200
MAX_SCAN = 2000
MAX_BACKFILL_MINUTES = 1440
MAX_WATCH_DURATION_SECONDS = 86400
MAX_WATCH_EVENTS = 10000
TASK_STATUSES = ("NotStarted", "InProgress", "Completed", "WaitingOnOthers", "Deferred")
EMAIL_DETAIL_FIELD_CHOICES = (
    "id",
    "subject",
    "sender",
    "to",
    "cc",
    "bcc",
    "datetime_received",
    "datetime_sent",
    "is_read",
    "has_attachments",
    "importance",
    "body_preview",
    "body",
    "body_format",
    "body_length",
    "body_truncated",
    "body_html",
    "unique_body_html",
    "conversation_id",
    "internet_message_id",
    "attachments",
)
MEETING_NOTIFY_CHOICES = ("none", "all")
MEETING_NOTIFY_MAP = {
    "none": "SendToNone",
    "all": "SendToAllAndSaveCopy",
}


def normalize_folder(value: Any) -> str:
    """Return a supported canonical folder name."""

    if not isinstance(value, str) or value.lower() not in FOLDER_NAMES:
        raise CliError(
            f"Unsupported folder: {value!r}.",
            code="INVALID_FOLDER",
            exit_code=2,
            details={"allowed": list(FOLDER_NAMES)},
        )
    return value.lower()


def validate_bounded_int(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    """Validate an integer received outside Click's option parser."""

    if isinstance(value, bool):
        parsed = None
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            parsed = None
    else:
        parsed = None
    if parsed is None or not minimum <= parsed <= maximum:
        raise CliError(
            f"{field} must be an integer between {minimum} and {maximum}.",
            code="INVALID_INPUT",
            exit_code=2,
            details={"field": field, "minimum": minimum, "maximum": maximum},
        )
    return parsed

def ensure_start_before_end(start: Any, end: Any, *, action: str) -> None:
    """Reject empty or reversed time ranges before contacting Exchange."""

    try:
        valid = start < end
    except TypeError as exc:
        raise CliError(
            f"{action} start and end values are not comparable.",
            code="INVALID_TIME_RANGE",
            exit_code=2,
        ) from exc
    if not valid:
        raise CliError(
            f"{action} start must be earlier than end.",
            code="INVALID_TIME_RANGE",
            exit_code=2,
            details={"action": action},
        )


def parse_field_list(value: str | None, *, allowed: tuple[str, ...]) -> list[str] | None:
    if value is None:
        return None
    fields = [part.strip() for part in value.split(",") if part.strip()]
    if not fields:
        raise CliError("At least one field is required.", code="INVALID_INPUT", exit_code=2)
    unknown = [field for field in fields if field not in allowed]
    if unknown:
        raise CliError(
            f"Unsupported fields: {', '.join(unknown)}.",
            code="INVALID_INPUT",
            exit_code=2,
            details={"allowed": list(allowed)},
        )
    return fields


def normalize_task_status(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliError("Invalid task status.", code="INVALID_INPUT", exit_code=2)
    canonical = next((status for status in TASK_STATUSES if status.lower() == value.lower()), None)
    if canonical is None:
        raise CliError(
            f"Unsupported task status: {value!r}.",
            code="INVALID_INPUT",
            exit_code=2,
            details={"allowed": list(TASK_STATUSES)},
        )
    return canonical


def require_confirmation(confirmed: bool, *, action: str) -> None:
    """Require an explicit non-interactive acknowledgement for risky actions."""

    if confirmed:
        return
    raise CliError(
        f"Action '{action}' requires --confirm.",
        code="CONFIRMATION_REQUIRED",
        exit_code=2,
        details={"action": action, "required_flag": "--confirm"},
    )


def _safe_attachment_name(name: Any) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise CliError("Attachment has an invalid filename.", code="INVALID_ATTACHMENT_NAME")
    if (
        name in {".", ".."}
        or "/" in name
        or "\\" in name
        or Path(name).is_absolute()
        or PureWindowsPath(name).is_absolute()
    ):
        raise CliError(
            f"Unsafe attachment filename: {name!r}.",
            code="INVALID_ATTACHMENT_NAME",
        )
    return name


def save_file_attachments(save_dir: Path, attachments: Iterable[Any]) -> list[Path]:
    """Save file attachments without traversal, duplicate names, or overwrites."""

    file_attachments = [item for item in attachments if isinstance(item, FileAttachment)]
    if not file_attachments:
        return []

    names = [_safe_attachment_name(item.name) for item in file_attachments]
    folded_names = [name.casefold() for name in names]
    if len(set(folded_names)) != len(folded_names):
        raise CliError(
            "Attachment names are not unique.",
            code="DUPLICATE_ATTACHMENT_NAME",
        )

    base = save_dir.expanduser().resolve(strict=False)
    targets = [base / name for name in names]
    for target in targets:
        try:
            target.resolve(strict=False).relative_to(base)
        except ValueError as exc:
            raise CliError(
                f"Attachment path escapes the destination: {target.name!r}.",
                code="INVALID_ATTACHMENT_NAME",
            ) from exc

    try:
        cur = base
        dirs_to_secure: list[Path] = []
        while cur != cur.parent and not cur.exists():
            dirs_to_secure.append(cur)
            cur = cur.parent
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        for d in dirs_to_secure:
            try:
                d.chmod(0o700)
            except OSError:
                pass
    except OSError as exc:
        raise CliError(
            f"Could not create attachment directory: {base}.",
            code="ATTACHMENT_SAVE_FAILED",
        ) from exc
    if not base.is_dir():
        raise CliError(
            f"Attachment destination is not a directory: {base}.",
            code="ATTACHMENT_SAVE_FAILED",
        )

    for target in targets:
        if target.exists() or target.is_symlink():
            raise CliError(
                f"Attachment target already exists: {target}.",
                code="ATTACHMENT_EXISTS",
                details={"path": str(target)},
            )

    created: list[Path] = []
    try:
        for attachment, target in zip(file_attachments, targets, strict=True):
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(target)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(attachment.content)
    except Exception as exc:
        for path in created:
            path.unlink(missing_ok=True)
        raise CliError(
            "Could not save all attachments safely.",
            code="ATTACHMENT_SAVE_FAILED",
        ) from exc

    return targets
