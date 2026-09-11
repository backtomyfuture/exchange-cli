"""Task listing with Exchange-safe status filtering."""

from __future__ import annotations

from .query import scan_matching, take_page
from .serializers import serialize_task
from .validation import MAX_SCAN, normalize_task_status


def list_tasks(account, *, limit: int, status: str | None, scan_limit: int = MAX_SCAN) -> tuple[list[dict], bool]:
    queryset = account.tasks.all().order_by("-due_date")
    wanted = normalize_task_status(status)
    if wanted is None:
        page, truncated = take_page(queryset, limit)
        return [serialize_task(item) for item in page], truncated

    page, truncated = scan_matching(
        queryset,
        limit=limit,
        scan_limit=scan_limit,
        predicate=lambda item: str(getattr(item, "status", "") or "") == wanted,
    )
    return [serialize_task(item) for item in page], truncated
