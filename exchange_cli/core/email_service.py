"""Email folder resolution, listing, and item lookup."""

from __future__ import annotations

from exchangelib.errors import ResponseMessageError
from exchangelib.folders import Folder

from .errors import NOT_FOUND_EXCEPTIONS, CliError
from .serializers import serialize_email_summary

WELL_KNOWN_FOLDERS = {
    # Inbox
    "inbox": "inbox",
    "收件箱": "inbox",
    # Sent
    "sent": "sent",
    "sentitems": "sent",
    "已发送": "sent",
    "已发送邮件": "sent",
    # Drafts
    "drafts": "drafts",
    "草稿": "drafts",
    "草稿箱": "drafts",
    # Trash / Deleted Items
    "trash": "trash",
    "deleteditems": "trash",
    "已删除": "trash",
    "已删除邮件": "trash",
    "回收站": "trash",
    "废纸篓": "trash",
    # Junk
    "junk": "junk",
    "junkemail": "junk",
    "垃圾邮件": "junk",
    # Outbox
    "outbox": "outbox",
    "发件箱": "outbox",
    # Archive
    "archive": "archive",
    "归档": "archive",
}


def is_email_item(item) -> bool:
    """Determine whether an EWS item should be presented as an email message."""
    from exchangelib import Message

    if isinstance(item, Message):
        return True
    return hasattr(item, "sender")


def _resolve_folder_by_id(account, folder_id: str):
    """Attempt to resolve an Exchange folder by its EWS folder ID."""
    try:
        if hasattr(account.root, "_folders_map") and folder_id in account.root._folders_map:
            return account.root._folders_map[folder_id]
    except Exception:
        pass

    try:
        from exchangelib.folders import FolderCollection

        folders = list(FolderCollection(account=account, folders=[Folder(root=account.root, id=folder_id)]).resolve())
        if folders and not isinstance(folders[0], Exception):
            return folders[0]
    except (*NOT_FOUND_EXCEPTIONS, ResponseMessageError, ValueError, TypeError):
        pass
    except Exception:
        raise
    return None


def resolve_mail_folder(account, folder_name: str):
    """Resolve a well-known name, folder path, folder name, or folder id."""

    if not isinstance(folder_name, str) or not folder_name.strip():
        raise CliError("Folder is required.", code="INVALID_FOLDER", exit_code=2)
    raw = folder_name.strip()
    lowered = raw.lower()

    if lowered in WELL_KNOWN_FOLDERS:
        folder = getattr(account, WELL_KNOWN_FOLDERS[lowered], None)
        if folder is not None:
            return folder

    if "/" in raw or "\\" in raw:
        return _resolve_folder_path(account, raw)

    # Check direct children under msg_folder_root (e.g. "收件箱", "Archive", "对话历史记录")
    try:
        return account.msg_folder_root / raw
    except Exception:
        pass

    # Check if raw looks like an EWS folder ID (base64 string without spaces)
    if len(raw) >= 30 and not any(c in raw for c in (" ", "\t", "\n")):
        resolved_folder = _resolve_folder_by_id(account, raw)
        if resolved_folder is not None:
            return resolved_folder

    # Check subfolders by name anywhere under msg_folder_root (e.g. "日常监察任务单", "Untitled Folder")
    try:
        matches = list(account.msg_folder_root.glob(f"**/{raw}"))
        if matches:
            return matches[0]
    except Exception:
        pass

    # Fallback ID check
    if len(raw) >= 10 and not any(c in raw for c in (" ", "\t", "\n")):
        resolved_folder = _resolve_folder_by_id(account, raw)
        if resolved_folder is not None:
            return resolved_folder

    raise CliError(f"Folder not found: {raw}.", code="NOT_FOUND")


def _resolve_folder_path(account, path: str):
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if not parts:
        raise CliError("Folder path is empty.", code="INVALID_FOLDER", exit_code=2)
    current = account.msg_folder_root
    first_lower = parts[0].lower()
    if first_lower in WELL_KNOWN_FOLDERS:
        well_known_folder = getattr(account, WELL_KNOWN_FOLDERS[first_lower], None)
        if well_known_folder is not None:
            current = well_known_folder
            parts = parts[1:]
    for part in parts:
        try:
            current = current / part
        except Exception as exc:
            raise CliError(f"Folder not found: {path}.", code="NOT_FOUND") from exc
    return current


def scan_email_page(queryset, limit: int, scan_limit: int = 2000) -> tuple[list, bool, int]:
    """Take up to `limit` email items, skipping non-email items such as contacts or tasks."""
    try:
        initial_page = list(queryset[: limit + 1])
    except Exception:
        initial_page = []

    if all(is_email_item(item) for item in initial_page):
        return initial_page[:limit], len(initial_page) > limit, 0

    has_more_items = len(initial_page) > limit
    email_items = []
    skipped_items = 0
    scanned = 0
    exhausted = not has_more_items

    for item in initial_page:
        scanned += 1
        if is_email_item(item):
            email_items.append(item)
            if len(email_items) >= limit:
                break
        else:
            skipped_items += 1

    if has_more_items and len(email_items) < limit:
        try:
            for item in queryset[scanned:]:
                scanned += 1
                if scanned > scan_limit:
                    exhausted = False
                    break
                if is_email_item(item):
                    email_items.append(item)
                    if len(email_items) >= limit:
                        break
                else:
                    skipped_items += 1
        except Exception:
            pass

    truncated = False
    if len(email_items) >= limit and has_more_items:
        try:
            for extra in queryset[scanned:]:
                if is_email_item(extra):
                    truncated = True
                    break
        except Exception:
            truncated = has_more_items

    return email_items[:limit], truncated or not exhausted, skipped_items


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
) -> tuple[list[dict], bool, int]:
    folder = resolve_mail_folder(account, folder_name)
    queryset = folder.filter(is_read=False) if unread else folder.all()
    projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
    page, truncated, skipped_items = scan_email_page(projected.order_by("-datetime_received"), limit)
    return [serialize_email_summary(item, include_body_preview=with_preview) for item in page], truncated, skipped_items


def find_message(account, message_id: str):
    folders = [account.inbox, account.sent, account.drafts, account.trash, account.junk]
    for folder in folders:
        try:
            item = folder.get(id=message_id)
            if item is not None and is_email_item(item):
                return item
        except (*NOT_FOUND_EXCEPTIONS, ResponseMessageError):
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
