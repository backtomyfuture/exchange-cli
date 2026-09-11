"""Bounded listing helpers that always report truncation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .validation import MAX_SCAN


def take_page(queryset, limit: int) -> tuple[list[Any], bool]:
    """Return at most `limit` items and whether more results exist."""

    page = list(queryset[: limit + 1])
    return page[:limit], len(page) > limit


def scan_matching(
    items: Iterable[Any],
    *,
    limit: int,
    predicate: Callable[[Any], bool],
    scan_limit: int = MAX_SCAN,
) -> tuple[list[Any], bool]:
    """Filter client-side with a hard scan cap so matching items are not silently dropped."""

    matches: list[Any] = []
    scanned = 0
    scan_exhausted = True
    for item in items:
        scanned += 1
        if scanned > scan_limit:
            scan_exhausted = False
            break
        if not predicate(item):
            continue
        matches.append(item)
        if len(matches) > limit:
            scan_exhausted = False
            break
    truncated = len(matches) > limit or not scan_exhausted
    return matches[:limit], truncated
