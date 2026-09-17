"""exchange-cli folder {list, tree, create, rename, move, delete, empty}."""

import click

from ..core.cli import get_account
from ..core.email_service import _validate_folder_input, resolve_mail_folder
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.folder_service import (
    create_mail_folder,
    delete_mail_folder,
    empty_mail_folder,
    move_mail_folder,
    rename_mail_folder,
    select_folder_delete_type,
    validate_new_folder_name,
)
from ..core.output import OutputFormatter
from ..core.serializers import serialize_folder
from ..core.validation import require_confirmation


def get_connection(ctx):
    return get_account(ctx)


def _folder_ref(value: str) -> str:
    return _validate_folder_input(value)


def _walk_tree(folder, depth=0, parent_path=""):
    current_name = getattr(folder, "name", "") or ""
    current_path = f"{parent_path}/{current_name}" if parent_path else current_name
    node = serialize_folder(folder, path=current_path)
    node["depth"] = depth
    items = [node]
    for child in getattr(folder, "children", []):
        items.extend(_walk_tree(child, depth + 1, current_path))
    return items


@click.group("folder")
@click.pass_context
def folder(ctx):
    """Mail-folder browsing and lifecycle management."""


@folder.command("list")
@click.pass_context
def folder_list(ctx):
    """List well-known and top-level folders."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        folders = list(account.msg_folder_root.children)
        results = [serialize_folder(folder_obj, path=getattr(folder_obj, "name", "") or "") for folder_obj in folders]
        formatter.success(results, count=len(results))
    except Exception as exc:
        raise classify_exception(exc) from exc


@folder.command("tree")
@click.pass_context
def folder_tree(ctx):
    """Display the folder hierarchy as a tree."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        tree = []
        for folder_obj in account.msg_folder_root.children:
            tree.extend(_walk_tree(folder_obj))
        formatter.success(tree, count=len(tree))
    except Exception as exc:
        raise classify_exception(exc) from exc


@folder.command("create")
@click.argument("name")
@click.option("--parent", "parent_ref", default=None, help="Parent folder; omit to create at mailbox root")
@click.option("--dry-run", is_flag=True, default=False, help="Validate without creating the folder")
@click.pass_context
def folder_create(ctx, name, parent_ref, dry_run):
    """Create a mail folder at the root or below an existing folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    name = validate_new_folder_name(name)
    parent_ref = _folder_ref(parent_ref) if parent_ref is not None else None
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "folder.create",
                "preview": {"name": name, "parent": parent_ref or "root", "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        parent = resolve_mail_folder(account, parent_ref) if parent_ref else account.msg_folder_root
        created = create_mail_folder(parent, name=name)
        formatter.success(
            {
                "message": "Folder created",
                "folder": serialize_folder(created),
                "parent": getattr(parent, "name", "root") or "root",
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@folder.command("rename")
@click.argument("folder_ref")
@click.option("--name", required=True, help="New single-segment folder name")
@click.option("--dry-run", is_flag=True, default=False, help="Validate without renaming the folder")
@click.pass_context
def folder_rename(ctx, folder_ref, name, dry_run):
    """Rename a non-system mail folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_ref = _folder_ref(folder_ref)
    name = validate_new_folder_name(name)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "folder.rename",
                "preview": {"folder": folder_ref, "name": name, "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        target = resolve_mail_folder(account, folder_ref)
        renamed = rename_mail_folder(target, name=name)
        formatter.success({"message": "Folder renamed", "folder": serialize_folder(renamed), "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@folder.command("move")
@click.argument("folder_ref")
@click.option("--parent", "parent_ref", required=True, help="Destination parent folder")
@click.option("--dry-run", is_flag=True, default=False, help="Validate without moving the folder")
@click.pass_context
def folder_move(ctx, folder_ref, parent_ref, dry_run):
    """Move a non-system mail folder under another folder."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_ref = _folder_ref(folder_ref)
    parent_ref = _folder_ref(parent_ref)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "folder.move",
                "preview": {"folder": folder_ref, "parent": parent_ref, "requires_confirm": False},
            }
        )
        return
    try:
        account = get_connection(ctx)
        target = resolve_mail_folder(account, folder_ref)
        parent = resolve_mail_folder(account, parent_ref)
        if getattr(target, "id", None) and getattr(target, "id", None) == getattr(parent, "id", None):
            raise CliError("A folder cannot be its own parent.", code="INVALID_FOLDER_STATE", exit_code=2)
        moved = move_mail_folder(target, parent=parent)
        formatter.success(
            {
                "message": "Folder moved",
                "folder": serialize_folder(moved),
                "parent": getattr(parent, "name", parent_ref),
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@folder.command("delete")
@click.argument("folder_ref")
@click.option("--permanent", is_flag=True, default=False, help="Hard-delete the folder and its contents")
@click.option("--soft", is_flag=True, default=False, help="Soft-delete the folder into Recoverable Items")
@click.option("--dry-run", is_flag=True, default=False, help="Preview deletion without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def folder_delete(ctx, folder_ref, permanent, soft, dry_run, confirm):
    """Delete a non-system mail folder; default is move to Deleted Items."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_ref = _folder_ref(folder_ref)
    delete_type, action = select_folder_delete_type(permanent=permanent, soft=soft)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "folder.delete",
                "preview": {
                    "folder": folder_ref,
                    "deletion": action,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="folder.delete")
    try:
        account = get_connection(ctx)
        target = resolve_mail_folder(account, folder_ref)
        deleted = serialize_folder(target)
        delete_mail_folder(target, delete_type=delete_type)
        formatter.success(
            {"message": "Folder deleted", "folder": deleted, "action": action, "outcome": "succeeded"}
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@folder.command("empty")
@click.argument("folder_ref")
@click.option(
    "--include-subfolders",
    is_flag=True,
    default=False,
    help="Also delete every child folder and its contents",
)
@click.option(
    "--permanent",
    is_flag=True,
    default=False,
    help="Hard-delete items instead of moving them to Deleted Items",
)
@click.option("--soft", is_flag=True, default=False, help="Soft-delete items into Recoverable Items")
@click.option("--dry-run", is_flag=True, default=False, help="Preview emptying the folder without changing Exchange")
@click.option("--confirm", is_flag=True, help="Confirm emptying the folder")
@click.pass_context
def folder_empty(ctx, folder_ref, include_subfolders, permanent, soft, dry_run, confirm):
    """Empty a mail folder using an explicit Exchange deletion mode."""
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    folder_ref = _folder_ref(folder_ref)
    delete_type, action = select_folder_delete_type(permanent=permanent, soft=soft)
    if dry_run:
        formatter.success(
            {
                "dry_run": True,
                "action": "folder.empty",
                "preview": {
                    "folder": folder_ref,
                    "deletion": action,
                    "include_subfolders": include_subfolders,
                    "requires_confirm": True,
                },
            }
        )
        return
    require_confirmation(confirm, action="folder.empty")
    try:
        account = get_connection(ctx)
        target = resolve_mail_folder(account, folder_ref)
        empty_mail_folder(target, delete_type=delete_type, include_subfolders=include_subfolders)
        formatter.success(
            {
                "message": "Folder emptied",
                "folder": serialize_folder(target),
                "action": action,
                "include_subfolders": include_subfolders,
                "outcome": "succeeded",
            }
        )
    except Exception as exc:
        raise classify_write_exception(exc) from exc
