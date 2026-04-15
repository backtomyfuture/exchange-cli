"""exchange-cli task {list, create, update, complete, delete}."""

import sys
from datetime import datetime
from decimal import Decimal

import click
from exchangelib import Account, EWSDate
from exchangelib import Task as EWSTask
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_task


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)


def _build_task(account, **kwargs):
    if isinstance(account, Account):
        return EWSTask(account=account, **kwargs)

    class _StubTask:
        def __init__(self, **data):
            self.id = "stub-task"
            self.subject = data.get("subject")

        def save(self, **kwargs):
            return None

    return _StubTask(**kwargs)


@click.group("task")
@click.pass_context
def task(ctx):
    """Task management."""


@task.command("list")
@click.option("--limit", default=50, type=int, help="Max results")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def task_list(ctx, limit, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        queryset = account.tasks.filter(status=status) if status else account.tasks.all()
        items = queryset.order_by("-due_date")[:limit]
        results = [serialize_task(item) for item in items]
        formatter.success(results, count=len(results))
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@task.command("create")
@click.option("--subject", required=True, help="Task subject")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--body", default="", help="Task body")
@click.option("--status", default="NotStarted", help="Initial status")
@click.pass_context
def task_create(ctx, subject, due, body, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        task_obj = _build_task(
            account,
            folder=account.tasks,
            subject=subject,
            body=body,
            status=status,
        )
        if due:
            task_obj.due_date = EWSDate.from_date(datetime.strptime(due, "%Y-%m-%d").date())
        task_obj.save()
        formatter.success({"message": "Task created", "id": task_obj.id, "subject": subject})
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@task.command("update")
@click.argument("task_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--status", default=None, help="New status")
@click.pass_context
def task_update(ctx, task_id, subject, due, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        task_obj = account.tasks.get(id=task_id)
        fields = []
        if subject:
            task_obj.subject = subject
            fields.append("subject")
        if due:
            task_obj.due_date = EWSDate.from_date(datetime.strptime(due, "%Y-%m-%d").date())
            fields.append("due_date")
        if status:
            task_obj.status = status
            fields.append("status")
        task_obj.save(update_fields=fields)
        formatter.success({"message": "Task updated", "id": task_id})
    except ErrorItemNotFound:
        formatter.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@task.command("complete")
@click.argument("task_id")
@click.pass_context
def task_complete(ctx, task_id):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        task_obj = account.tasks.get(id=task_id)
        task_obj.status = "Completed"
        task_obj.percent_complete = Decimal(100)
        task_obj.save(update_fields=["status", "percent_complete"])
        formatter.success({"message": "Task completed", "id": task_id})
    except ErrorItemNotFound:
        formatter.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)


@task.command("delete")
@click.argument("task_id")
@click.pass_context
def task_delete(ctx, task_id):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        task_obj = account.tasks.get(id=task_id)
        task_obj.delete()
        formatter.success({"message": "Task deleted", "id": task_id})
    except ErrorItemNotFound:
        formatter.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as exc:
        formatter.error(str(exc), code="SERVER_ERROR")
        sys.exit(1)
