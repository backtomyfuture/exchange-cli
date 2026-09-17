"""Email folder resolution, listing, and item lookup."""

from __future__ import annotations

from pathlib import Path

from exchangelib import FileAttachment
from exchangelib.errors import ResponseMessageError
from exchangelib.folders import Folder

from .errors import NOT_FOUND_EXCEPTIONS, CliError
from .serializers import serialize_email_summary
from .validation import MAX_SCAN

WELL_KNOWN_FOLDERS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    # Inbox
    "inbox": ("inbox", ("收件箱", "Inbox")),
    "收件箱": ("inbox", ("收件箱", "Inbox")),
    # Sent
    "sent": ("sent", ("已发送邮件", "已发送", "Sent Items")),
    "sentitems": ("sent", ("已发送邮件", "已发送", "Sent Items")),
    "已发送": ("sent", ("已发送邮件", "已发送", "Sent Items")),
    "已发送邮件": ("sent", ("已发送邮件", "已发送", "Sent Items")),
    # Drafts
    "drafts": ("drafts", ("草稿", "草稿箱", "Drafts")),
    "草稿": ("drafts", ("草稿", "草稿箱", "Drafts")),
    "草稿箱": ("drafts", ("草稿", "草稿箱", "Drafts")),
    # Trash / Deleted Items
    "trash": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    "deleteditems": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    "已删除": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    "已删除邮件": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    "回收站": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    "废纸篓": ("trash", ("已删除邮件", "已删除", "回收站", "废纸篓", "Deleted Items")),
    # Junk
    "junk": ("junk", ("垃圾邮件", "Junk Email")),
    "junkemail": ("junk", ("垃圾邮件", "Junk Email")),
    "垃圾邮件": ("junk", ("垃圾邮件", "Junk Email")),
    # Outbox
    "outbox": ("outbox", ("发件箱", "Outbox")),
    "发件箱": ("outbox", ("发件箱", "Outbox")),
    # Archive
    "archive": (None, ("Archive", "归档", "封存")),
    "归档": (None, ("Archive", "归档", "封存")),
    # Recoverable Items (the EWS soft-delete dumpster)
    "recoverable-deletions": ("recoverable_items_deletions", ()),
    "recoverable-items-deletions": ("recoverable_items_deletions", ()),
    "recoverable-root": ("recoverable_items_root", ()),
}

EWS_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=_-")


def _looks_like_ews_id(s: str) -> bool:
    return len(s) >= 40 and not any(c.isspace() for c in s) and set(s).issubset(EWS_ID_CHARS)


def _validate_folder_input(folder_name: str) -> str:
    """Validate folder name input against path traversal and empty/dot-only paths."""
    if not isinstance(folder_name, str) or not folder_name.strip():
        raise CliError("Folder is required.", code="INVALID_FOLDER", exit_code=2)
    raw = folder_name.strip()
    # Check for path traversal segments
    parts = [part.strip() for part in raw.replace("\\", "/").split("/")]
    for p in parts:
        if p == "..":
            raise CliError(
                f"Invalid folder path '{raw}': traversal with '..' is not allowed.",
                code="INVALID_FOLDER",
                exit_code=2,
            )
    # Check if path consists only of dots or slashes
    non_dot_parts = [p for p in parts if p and p != "."]
    if not non_dot_parts:
        raise CliError(f"Invalid folder path '{raw}'.", code="INVALID_FOLDER", exit_code=2)
    return raw


def _resolve_well_known_folder(account, name: str):
    entry = WELL_KNOWN_FOLDERS.get(name.lower())
    if not entry:
        return None
    attr_name, candidate_names = entry
    if attr_name:
        folder = getattr(account, attr_name, None)
        if folder is not None:
            return folder
    # Fallback to candidate names under msg_folder_root (e.g. Archive / 归档)
    if hasattr(account, "msg_folder_root") and account.msg_folder_root:
        for cand in candidate_names:
            try:
                cand_folder = account.msg_folder_root / cand
                if cand_folder is not None:
                    return cand_folder
            except Exception:
                pass
        try:
            lowered_cands = {c.lower() for c in candidate_names}
            for child in getattr(account.msg_folder_root, "children", []):
                if getattr(child, "name", "").lower() in lowered_cands:
                    return child
        except Exception:
            pass
    return None


def is_email_item(item) -> bool:
    """Determine whether an EWS item should be presented as an email message."""
    from exchangelib import Message

    if isinstance(item, Message):
        return True
    return hasattr(item, "sender")


def _resolve_folder_by_id(account, folder_id: str, *, root=None):
    """Attempt to resolve an Exchange folder by its EWS folder ID."""
    root = root or account.root
    try:
        if hasattr(root, "_folders_map") and folder_id in root._folders_map:
            return root._folders_map[folder_id]
    except Exception:
        pass

    try:
        from exchangelib.folders import FolderCollection

        folders = list(FolderCollection(account=account, folders=[Folder(root=root, id=folder_id)]).resolve())
        if folders and not isinstance(folders[0], Exception):
            return folders[0]
    except (*NOT_FOUND_EXCEPTIONS, ResponseMessageError, ValueError, TypeError):
        pass
    except Exception:
        raise

    try:
        if hasattr(root, "get_folder"):
            return root.get_folder(Folder(root=root, id=folder_id))
    except (*NOT_FOUND_EXCEPTIONS, ResponseMessageError, ValueError, TypeError):
        pass
    except Exception:
        raise

    return None


def resolve_mail_folder(account, folder_name: str):
    """Resolve a well-known name, folder path, folder name, or folder id."""

    raw = _validate_folder_input(folder_name)

    well_known = _resolve_well_known_folder(account, raw)
    if well_known is not None:
        return well_known

    # Prioritize EWS folder IDs (length >= 40, base64 char set, can contain '/')
    if _looks_like_ews_id(raw):
        resolved_folder = _resolve_folder_by_id(account, raw)
        if resolved_folder is not None:
            return resolved_folder

    if "/" in raw or "\\" in raw:
        return _resolve_folder_path(account, raw)

    # Check direct children under msg_folder_root (e.g. "收件箱", "Archive", "对话历史记录")
    try:
        return account.msg_folder_root / raw
    except Exception:
        pass

    # Check children case-insensitively
    try:
        raw_lower = raw.lower()
        for child in getattr(account.msg_folder_root, "children", []):
            if getattr(child, "name", "").lower() == raw_lower:
                return child
    except Exception:
        pass

    # Check subfolders by name anywhere under msg_folder_root (e.g. "日常监察任务单", "Untitled Folder")
    try:
        matches = list(account.msg_folder_root.glob(f"**/{raw}"))
        if matches:
            return matches[0]
    except Exception:
        pass

    # Fallback ID check (shorter IDs >= 10 chars)
    if len(raw) >= 10 and not any(c.isspace() for c in raw) and set(raw).issubset(EWS_ID_CHARS):
        resolved_folder = _resolve_folder_by_id(account, raw)
        if resolved_folder is not None:
            return resolved_folder

    raise CliError(f"Folder not found: {raw}.", code="NOT_FOUND")


def _resolve_folder_path(account, path: str):
    parts = [part.strip() for part in path.replace("\\", "/").split("/") if part.strip() and part.strip() != "."]
    if not parts:
        raise CliError("Folder path is empty.", code="INVALID_FOLDER", exit_code=2)
    current = account.msg_folder_root
    first_lower = parts[0].lower()
    well_known_folder = _resolve_well_known_folder(account, first_lower)
    if well_known_folder is not None:
        current = well_known_folder
        parts = parts[1:]
    for part in parts:
        try:
            current = current / part
        except Exception as exc:
            raise CliError(f"Folder not found: {path}.", code="NOT_FOUND") from exc
    return current


def resolve_archive_folder(account, folder_name: str):
    """Resolve a destination within the account's online archive mailbox.

    ArchiveItem requires a folder in the archive mailbox. Reusing
    ``resolve_mail_folder`` here would silently target a same-named folder in
    the primary mailbox, which is a move rather than an archive operation.
    """
    raw = _validate_folder_input(folder_name)
    lowered = raw.lower()
    inbox_aliases = {"inbox", "archive", "archive-inbox", "归档", "封存"}
    if lowered in inbox_aliases:
        return account.archive_inbox

    archive_root = account.archive_root
    if _looks_like_ews_id(raw):
        resolved_folder = _resolve_folder_by_id(account, raw, root=archive_root)
        if resolved_folder is not None:
            return resolved_folder

    parts = [part.strip() for part in raw.replace("\\", "/").split("/") if part.strip() and part.strip() != "."]
    if not parts:
        raise CliError("Archive folder path is empty.", code="INVALID_FOLDER", exit_code=2)

    current = account.archive_msg_folder_root
    if parts[0].lower() in inbox_aliases:
        current = account.archive_inbox
        parts = parts[1:]
    for part in parts:
        try:
            current = current / part
        except Exception as exc:
            raise CliError(f"Archive folder not found: {raw}.", code="NOT_FOUND") from exc
    return current


def scan_email_page(
    queryset,
    limit: int,
    *,
    offset: int = 0,
    scan_limit: int = MAX_SCAN,
) -> tuple[list, bool, int, int | None]:
    """Take a bounded, offset-based page of email items from a mixed-item folder.

    EWS offsets address all items in a folder, not only messages. To avoid
    losing a message after contacts, tasks, or calendar items are skipped, the
    next offset always points immediately after the final returned email. The
    following request may scan some non-email items again, but it cannot skip a
    message. Folder changes between calls can still make EWS absolute offsets
    unstable, which is inherent to the upstream API.
    """
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if scan_limit < 1:
        raise ValueError("scan_limit must be positive")

    email_items = []
    skipped_items = 0
    scanned = 0
    scan_offset = offset
    next_offset_after_result: int | None = None

    while scanned < scan_limit:
        # Start with a small, efficient EWS page. Keep scanning only when
        # mixed item types make that insufficient to establish completeness.
        requested = min(limit + 1, scan_limit - scanned)
        raw_items = list(queryset[scan_offset : scan_offset + requested])
        if not raw_items:
            return email_items, False, skipped_items, None

        for item in raw_items:
            scanned += 1
            scan_offset += 1
            if is_email_item(item):
                if len(email_items) == limit:
                    return email_items, True, skipped_items, next_offset_after_result
                email_items.append(item)
                next_offset_after_result = scan_offset
            else:
                skipped_items += 1

        # A short EWS slice proves there is no following raw item. The current
        # page therefore contains every remaining email.
        if len(raw_items) < requested:
            return email_items, False, skipped_items, None

    # The bounded scan prevents a pathological mixed folder from turning one
    # CLI request into an unbounded server traversal. Advertise incompleteness
    # and provide a safe resume point.
    resume_offset = next_offset_after_result if len(email_items) == limit else scan_offset
    return email_items, True, skipped_items, resume_offset


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
    offset: int,
    unread: bool,
    with_preview: bool,
) -> tuple[list[dict], bool, int, int | None]:
    folder = resolve_mail_folder(account, folder_name)
    queryset = folder.filter(is_read=False) if unread else folder.all()
    projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
    page, truncated, skipped_items, next_offset = scan_email_page(
        projected.order_by("-datetime_received"), limit, offset=offset
    )
    summaries = [serialize_email_summary(item, include_body_preview=with_preview) for item in page]
    return summaries, truncated, skipped_items, next_offset


def find_message(account, message_id: str):
    """Return an email item by EWS ID, regardless of its containing folder.

    ``Account.fetch()`` maps to EWS ``GetItem`` and does not require knowing the
    item's folder. Searching a fixed set of distinguished folders made IDs
    returned by ``email list --folder <custom-folder>`` unusable with ``read``,
    ``move``, ``reply``, and the other ID-based commands.

    The folder scan remains as a compatibility fallback for lightweight test
    doubles and alternate account-like clients that do not implement ``fetch``.
    """
    fetch = getattr(account, "fetch", None)
    if callable(fetch):
        try:
            for item in fetch(ids=[message_id]):
                if isinstance(item, Exception):
                    if isinstance(item, NOT_FOUND_EXCEPTIONS):
                        return None
                    raise item
                return item if item is not None and is_email_item(item) else None
            return None
        except NOT_FOUND_EXCEPTIONS:
            return None
        except (AttributeError, TypeError):
            # Some account-like clients expose a non-compatible ``fetch``
            # method. Preserve the original folder-based lookup for them.
            pass

    folders = [account.inbox, account.sent, account.drafts, account.trash, account.junk]
    for folder in folders:
        try:
            item = folder.get(id=message_id)
            if item is not None and is_email_item(item):
                return item
        except NOT_FOUND_EXCEPTIONS:
            continue
    return None


def require_message(account, message_id: str):
    message = find_message(account, message_id)
    if message is None:
        raise CliError(f"Message not found: {message_id}", code="NOT_FOUND")
    return message


def require_draft(account, draft_id: str):
    message = require_message(account, draft_id)
    if not bool(getattr(message, "is_draft", False)):
        raise CliError(f"Draft not found: {draft_id}", code="NOT_FOUND")
    return message


def require_matching_changekey(message, expected_changekey: str | None) -> None:
    if expected_changekey is None:
        return
    actual = getattr(message, "changekey", None)
    if expected_changekey != actual:
        raise CliError(
            "Message changed since the supplied changekey was read.",
            code="CONFLICT",
            exit_code=1,
            details={"expected_changekey": expected_changekey, "actual_changekey": actual},
        )


def _attachment_id_value(attachment) -> str | None:
    attachment_id = getattr(attachment, "attachment_id", None)
    if attachment_id is None:
        return None
    if isinstance(attachment_id, str):
        return attachment_id
    value = getattr(attachment_id, "id", None)
    return value if value is None or isinstance(value, str) else str(value)


def attach_file_attachments(message, *, files, inline_files=None):
    """Attach local files to a message. Saved items are updated immediately by EWS."""
    created = []
    for path in files or []:
        attachment = FileAttachment(name=path.name, content=Path(path).read_bytes())
        message.attach(attachment)
        created.append(attachment)
    for path, content_id in inline_files or []:
        attachment = FileAttachment(
            name=path.name,
            content=Path(path).read_bytes(),
            is_inline=True,
            content_id=content_id,
        )
        message.attach(attachment)
        created.append(attachment)
    return created


def select_message_attachments(message, *, attachment_ids=(), names=()):
    """Resolve saved attachments by EWS id and/or unique filename."""
    wanted_ids = [value.strip() for value in attachment_ids]
    wanted_names = [value.strip() for value in names]
    if not wanted_ids and not wanted_names:
        raise CliError("Provide --attachment-id and/or --name.", code="INVALID_INPUT", exit_code=2)
    if any(not value for value in wanted_ids):
        raise CliError("--attachment-id cannot be empty.", code="INVALID_INPUT", exit_code=2)
    if any(not value for value in wanted_names):
        raise CliError("--name cannot be empty.", code="INVALID_INPUT", exit_code=2)

    attachments = list(getattr(message, "attachments", None) or [])
    selected: list = []
    seen: set[int] = set()

    def _add(attachment) -> None:
        marker = id(attachment)
        if marker not in seen:
            seen.add(marker)
            selected.append(attachment)

    for attachment_id in wanted_ids:
        matches = [item for item in attachments if _attachment_id_value(item) == attachment_id]
        if not matches:
            raise CliError(
                f"Attachment not found: {attachment_id}",
                code="NOT_FOUND",
                details={"attachment_id": attachment_id},
            )
        _add(matches[0])

    for name in wanted_names:
        matches = [item for item in attachments if getattr(item, "name", None) == name]
        if not matches:
            raise CliError(f"Attachment not found: {name}", code="NOT_FOUND", details={"name": name})
        if len(matches) > 1:
            raise CliError(
                f"Multiple attachments named {name!r}; use --attachment-id.",
                code="INVALID_INPUT",
                exit_code=2,
                details={"name": name, "ids": [_attachment_id_value(item) for item in matches]},
            )
        _add(matches[0])
    return selected


def detach_message_attachments(message, attachments) -> None:
    message.detach(list(attachments))


def set_message_read_state(message, *, is_read: bool) -> None:
    message.is_read = is_read
    message.save(update_fields=["is_read"])


def move_message(message, account, folder_name: str):
    folder = resolve_mail_folder(account, folder_name)
    message.move(folder)
    return folder


def copy_message(message, account, folder_name: str):
    folder = resolve_mail_folder(account, folder_name)
    return folder, message.copy(folder)


def archive_message(message, account, folder_name: str):
    folder = resolve_archive_folder(account, folder_name)
    return folder, message.archive(folder)


def set_message_junk_state(message, *, is_junk: bool, move_item: bool) -> None:
    message.mark_as_junk(is_junk=is_junk, move_item=move_item)


def respond_to_meeting_request(
    message,
    *,
    response: str,
    body=None,
    proposed_start=None,
    proposed_end=None,
    save_copy: bool,
):
    """Send one of the native EWS responses to a meeting request."""
    from exchangelib.items import MeetingRequest

    if not isinstance(message, MeetingRequest):
        raise CliError(
            "The item is not a meeting request.",
            code="INVALID_MESSAGE_TYPE",
            exit_code=2,
        )

    method_name = {
        "accept": "accept",
        "tentative": "tentatively_accept",
        "decline": "decline",
    }[response]
    kwargs = {}
    if body is not None:
        kwargs["body"] = body
    if proposed_start is not None:
        kwargs["proposed_start"] = proposed_start
    if proposed_end is not None:
        kwargs["proposed_end"] = proposed_end
    return getattr(message, method_name)(
        message_disposition="SendAndSaveCopy" if save_copy else "SendOnly",
        **kwargs,
    )


def update_message(
    message,
    *,
    values: dict[str, object],
    draft_only_fields: set[str],
    expected_changekey: str | None = None,
    conflict_resolution: str = "AutoResolve",
) -> list[str]:
    """Update explicit EWS fields and preserve optimistic-concurrency intent."""
    changed_fields = list(values)
    if not changed_fields:
        raise CliError("At least one update option is required.", code="INVALID_INPUT", exit_code=2)

    if expected_changekey is not None and expected_changekey != getattr(message, "changekey", None):
        raise CliError(
            "Message changed since the supplied changekey was read.",
            code="CONFLICT",
            exit_code=1,
            details={"expected_changekey": expected_changekey, "actual_changekey": getattr(message, "changekey", None)},
        )

    draft_only = sorted(set(changed_fields) & draft_only_fields)
    if draft_only and not bool(getattr(message, "is_draft", False)):
        raise CliError(
            f"These fields can only be changed on a draft message: {', '.join(draft_only)}.",
            code="INVALID_MESSAGE_STATE",
            exit_code=2,
            details={"fields": draft_only},
        )

    for field, value in values.items():
        setattr(message, field, value)
    message.save(update_fields=changed_fields, conflict_resolution=conflict_resolution)
    return changed_fields


def delete_message(message, *, permanent: bool, soft: bool = False) -> str:
    if permanent and soft:
        raise CliError(
            "Choose either permanent deletion or soft deletion, not both.",
            code="INVALID_INPUT",
            exit_code=2,
        )
    if permanent:
        message.delete()
        return "hard_deleted"
    if soft:
        message.soft_delete()
        return "soft_deleted"
    message.move_to_trash()
    return "trashed"
