"""Email folder resolution, listing, and item lookup."""

from __future__ import annotations

from exchangelib.errors import DoesNotExist, ErrorItemNotFound
from exchangelib.folders import Folder

from .errors import CliError
from .query import take_page
from .serializers import serialize_email_summary

WELL_KNOWN_FOLDERS = {
    "inbox": "inbox",
    "sent": "sent",
    "drafts": "drafts",
    "trash": "trash",
    "junk": "junk",
}


def resolve_mail_folder(account, folder_name: str):
    """Resolve a well-known name, folder path, or folder id."""

    if not isinstance(folder_name, str) or not folder_name.strip():
        raise CliError("Folder is required.", code="INVALID_FOLDER", exit_code=2)
    raw = folder_name.strip()
    lowered = raw.lower()
    if lowered in WELL_KNOWN_FOLDERS:
        return getattr(account, WELL_KNOWN_FOLDERS[lowered])
    if "/" in raw or "\\" in raw:
        return _resolve_folder_path(account, raw)
    folder = Folder(root=account.root, id=raw)
    try:
        folder.refresh()
    except (DoesNotExist, ErrorItemNotFound, ValueError, TypeError) as exc:
        raise CliError(
            f"Folder not found: {raw}.",
            code="NOT_FOUND",
        ) from exc
    return folder


def _resolve_folder_path(account, path: str):
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if not parts:
        raise CliError("Folder path is empty.", code="INVALID_FOLDER", exit_code=2)
    current = account.msg_folder_root
    for part in parts:
        try:
            current = current / part
        except Exception as exc:
            raise CliError(f"Folder not found: {path}.", code="NOT_FOUND") from exc
    return current


def project_email_summary_fields(queryset, *, include_body_preview: bool):
    fields = [
        "subject",
        "sender",
        "to_recipients",
        "cc_recipients",
        "datetime_received",
        "datetime_sent",
        "is_read",
        "has_attachments",
        "importance",
    ]
    if include_body_preview:
        fields.append("text_body")
    try:
        return queryset.only(*fields)
    except (AttributeError, ValueError, TypeError):
        return queryset


def list_email_summaries(
    account,
    *,
    folder_name: str,
    limit: int,
    unread: bool,
    with_preview: bool,
) -> tuple[list[dict], bool]:
    folder = resolve_mail_folder(account, folder_name)
    queryset = folder.filter(is_read=False) if unread else folder.all()
    projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
    page, truncated = take_page(projected.order_by("-datetime_received"), limit)
    return [serialize_email_summary(item, include_body_preview=with_preview) for item in page], truncated


def find_message(account, message_id: str):
    folders = [account.inbox, account.sent, account.drafts, account.trash, account.junk]
    for folder in folders:
        try:
            return folder.get(id=message_id)
        except (DoesNotExist, ErrorItemNotFound):
            continue
    return None


def require_message(account, message_id: str):
    message = find_message(account, message_id)
    if message is None:
        raise CliError(f"Message not found: {message_id}", code="NOT_FOUND")
    return message


def set_message_read_state(message, *, is_read: bool) -> None:
    message.is_read = is_read
    message.save(update_fields=["is_read"])


def move_message(message, account, folder_name: str):
    folder = resolve_mail_folder(account, folder_name)
    message.move(folder)
    return folder


def delete_message(message, *, permanent: bool) -> str:
    if permanent:
        message.delete()
        return "deleted"
    message.move_to_trash()
    return "trashed"
