"""exchange-cli folder {list, tree}."""

import sys

import click

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_folder


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _walk_tree(folder, depth=0):
    node = serialize_folder(folder)
    node["depth"] = depth
    items = [node]
    for child in getattr(folder, "children", []):
        items.extend(_walk_tree(child, depth + 1))
    return items


@click.group("folder")
@click.pass_context
def folder(ctx):
    """Folder browsing."""


@folder.command("list")
@click.pass_context
def folder_list(ctx):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        folders = list(account.msg_folder_root.children)
        results = [serialize_folder(folder_obj) for folder_obj in folders]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@folder.command("tree")
@click.pass_context
def folder_tree(ctx):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        tree = []
        for folder_obj in account.msg_folder_root.children:
            tree.extend(_walk_tree(folder_obj))
        formatter.success(tree, count=len(tree))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
