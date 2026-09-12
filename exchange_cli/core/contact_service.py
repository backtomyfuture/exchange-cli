"""Personal contacts and Global Address List resolution."""

from __future__ import annotations

from exchangelib import Q
from exchangelib.errors import ErrorInvalidNameForNameResolution, ErrorNameResolutionNoResults

from .errors import CliError
from .query import take_page
from .serializers import serialize_contact, serialize_resolved_name


def list_contacts(account, *, limit: int) -> tuple[list[dict], bool]:
    page, truncated = take_page(account.contacts.all(), limit)
    return [serialize_contact(item) for item in page], truncated


def search_contacts(account, query: str, *, limit: int) -> tuple[list[dict], bool]:
    if not isinstance(query, str) or not query.strip():
        raise CliError("Query must be non-empty.", code="INVALID_INPUT", exit_code=2)
    criteria = Q(display_name__icontains=query.strip()) | Q(email_addresses__icontains=query.strip())
    page, truncated = take_page(account.contacts.filter(criteria), limit)
    return [serialize_contact(item) for item in page], truncated


def resolve_directory(account, query: str, *, limit: int) -> tuple[list[dict], bool]:
    if not isinstance(query, str) or not query.strip():
        raise CliError("Query must be non-empty.", code="INVALID_INPUT", exit_code=2)
    clean_query = query.strip()
    protocol = account.protocol
    # ResolveNames reads protocol.config.version directly. Touching protocol.version
    # forces exchangelib to detect the server version first.
    if protocol is None:
        raise CliError("Exchange protocol is unavailable.", code="CONNECTION_ERROR", retryable=True)
    _ = protocol.version
    try:
        matches = protocol.resolve_names(
            [clean_query],
            return_full_contact_data=True,
            search_scope="ActiveDirectory",
        )
    except ErrorInvalidNameForNameResolution as exc:
        raise CliError("Invalid name for name resolution.", code="INVALID_INPUT", exit_code=2) from exc
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
