"""Personal contacts and Global Address List resolution."""

from __future__ import annotations

from exchangelib import Q
from exchangelib.errors import ErrorNameResolutionNoResults

from .query import take_page
from .serializers import serialize_contact, serialize_resolved_name


def list_contacts(account, *, limit: int) -> tuple[list[dict], bool]:
    page, truncated = take_page(account.contacts.all(), limit)
    return [serialize_contact(item) for item in page], truncated


def search_contacts(account, query: str, *, limit: int) -> tuple[list[dict], bool]:
    criteria = Q(display_name__icontains=query) | Q(email_addresses__icontains=query)
    page, truncated = take_page(account.contacts.filter(criteria), limit)
    return [serialize_contact(item) for item in page], truncated


def resolve_directory(account, query: str, *, limit: int) -> tuple[list[dict], bool]:
    try:
        matches = account.protocol.resolve_names(
            [query],
            return_full_contact_data=True,
            search_scope="ActiveDirectory",
        )
    except ErrorNameResolutionNoResults:
        return [], False

    results: list[dict] = []
    for match in matches:
        if isinstance(match, Exception):
            continue
        mailbox, contact = _split_resolution(match)
        payload = serialize_resolved_name(mailbox, contact)
        if payload not in results:
            results.append(payload)
        if len(results) >= limit:
            break
    return results, len(matches) > limit


def _split_resolution(match):
    if isinstance(match, tuple) and len(match) == 2:
        return match[0], match[1]
    mailbox = match
    email = getattr(mailbox, "email_address", None)
    if email:
        return mailbox, None
    return None, match
