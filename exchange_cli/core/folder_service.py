"""Safe folder lifecycle operations built on exchangelib's Folder API."""

from __future__ import annotations

from exchangelib import Folder
from exchangelib.items import HARD_DELETE, MOVE_TO_DELETED_ITEMS, SOFT_DELETE

from .errors import CliError


def validate_new_folder_name(value: str) -> str:
    """Validate a single Exchange folder name, never a hierarchy path."""
    if not isinstance(value, str) or not value.strip():
        raise CliError("Folder name is required.", code="INVALID_FOLDER", exit_code=2)
    name = value.strip()
    if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise CliError(
            "Folder name must be one path segment without slashes, traversal markers, or NUL characters.",
            code="INVALID_FOLDER",
            exit_code=2,
        )
    if len(name) > 255:
        raise CliError("Folder name cannot exceed 255 characters.", code="INVALID_FOLDER", exit_code=2)
    return name


def select_folder_delete_type(*, permanent: bool, soft: bool) -> tuple[str, str]:
    """Choose the EWS deletion mode and a stable result label."""
    if permanent and soft:
        raise CliError(
            "Choose either permanent deletion or soft deletion, not both.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if permanent:
        return HARD_DELETE, "hard_deleted"
    if soft:
        return SOFT_DELETE, "soft_deleted"
    return MOVE_TO_DELETED_ITEMS, "moved_to_deleted_items"


def require_mutable_folder(folder, *, action: str) -> None:
    """Reject structural changes to distinguished system folders locally."""
    distinguished_id = getattr(folder, "DISTINGUISHED_FOLDER_ID", None)
    if (
        getattr(folder, "is_deletable", None) is False
        or getattr(folder, "is_distinguished", None) is True
        or (isinstance(distinguished_id, str) and bool(distinguished_id))
    ):
        raise CliError(
            f"The selected system folder cannot be {action}.",
            code="INVALID_FOLDER_STATE",
            exit_code=2,
        )


def create_mail_folder(parent, *, name: str):
    folder = Folder(parent=parent, name=name)
    folder.save()
    return folder


def rename_mail_folder(folder, *, name: str):
    require_mutable_folder(folder, action="renamed")
    folder.name = name
    folder.save(update_fields=["name"])
    return folder


def move_mail_folder(folder, *, parent):
    require_mutable_folder(folder, action="moved")
    folder.move(parent)
    return folder


def delete_mail_folder(folder, *, delete_type: str) -> None:
    require_mutable_folder(folder, action="deleted")
    folder.delete(delete_type=delete_type)


def empty_mail_folder(folder, *, delete_type: str, include_subfolders: bool) -> None:
    folder.empty(delete_type=delete_type, delete_sub_folders=include_subfolders)
