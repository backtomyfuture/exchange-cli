"""exchange-cli contact {list, search, resolve}."""

import click

from ..core.cli import get_account
from ..core.contact_service import list_contacts, resolve_directory, search_contacts
from ..core.errors import classify_exception
from ..core.output import OutputFormatter
from ..core.validation import MAX_RESULTS


def get_connection(ctx):
    return get_account(ctx)


@click.group("contact")
@click.pass_context
def contact(ctx):
    """Contacts."""


@contact.command("list")
@click.option("--limit", default=50, type=click.IntRange(1, MAX_RESULTS), help="Max contacts to return")
@click.pass_context
def contact_list(ctx, limit):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results, truncated = list_contacts(account, limit=limit)
        formatter.success(results, count=len(results), truncated=truncated)
    except Exception as exc:
        raise classify_exception(exc) from exc


@contact.command("search")
@click.argument("query")
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Max results")
@click.pass_context
def contact_search(ctx, query, limit):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results, truncated = search_contacts(account, query, limit=limit)
        formatter.success(results, count=len(results), truncated=truncated)
    except Exception as exc:
        raise classify_exception(exc) from exc


@contact.command("resolve")
@click.argument("query")
@click.option("--limit", default=20, type=click.IntRange(1, MAX_RESULTS), help="Max results")
@click.pass_context
def contact_resolve(ctx, query, limit):
    """Resolve a name or email against the company directory."""

    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results, truncated = resolve_directory(account, query, limit=limit)
        formatter.success(results, count=len(results), truncated=truncated)
    except Exception as exc:
        raise classify_exception(exc) from exc
