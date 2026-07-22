"""exchange-cli contact {list, search}."""

import click
from exchangelib import Q

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.errors import classify_exception
from ..core.output import OutputFormatter
from ..core.serializers import serialize_contact
from ..core.validation import MAX_RESULTS


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


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
        items = account.contacts.all()[:limit]
        results = [serialize_contact(contact_obj) for contact_obj in items]
        formatter.success(results, count=len(results))
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
        criteria = Q(display_name__icontains=query) | Q(email_addresses__icontains=query)
        items = account.contacts.filter(criteria)[:limit]
        results = [serialize_contact(contact_obj) for contact_obj in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc
