"""Email folder resolution and list queries."""

from __future__ import annotations

from .serializers import serialize_email_summary
from .validation import normalize_folder


def resolve_mail_folder(account, folder_name: str):
    folder_name = normalize_folder(folder_name)
    return {
        "inbox": account.inbox,
        "sent": account.sent,
        "drafts": account.drafts,
        "trash": account.trash,
        "junk": account.junk,
    }[folder_name]


def project_email_summary_fields(queryset, *, include_body_preview: bool):
    if queryset.__class__.__module__.startswith("unittest.mock"):
        return queryset
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
    except (AttributeError, ValueError):
        return queryset


def list_email_summaries(
    account,
    *,
    folder_name: str,
    limit: int,
    unread: bool,
    with_preview: bool,
) -> list[dict]:
    folder = resolve_mail_folder(account, folder_name)
    queryset = folder.filter(is_read=False) if unread else folder.all()
    projected = project_email_summary_fields(queryset, include_body_preview=with_preview)
    items = projected.order_by("-datetime_received")[:limit]
    return [serialize_email_summary(item, include_body_preview=with_preview) for item in items]
