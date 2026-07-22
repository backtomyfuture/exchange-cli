"""exchange-cli task {list, create, update, complete, delete}."""

from datetime import datetime
from decimal import Decimal

import click
from exchangelib import Account, EWSDate
from exchangelib import Task as EWSTask
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.errors import CliError, classify_exception
from ..core.output import OutputFormatter
from ..core.serializers import serialize_task
from ..core.validation import MAX_RESULTS, require_confirmation


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


def _parse_due_date(value: str) -> EWSDate:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise click.BadParameter("Use YYYY-MM-DD format.", param_hint="--due") from exc
    return EWSDate.from_date(parsed)


@click.group("task")
@click.pass_context
def task(ctx):
    """Task management."""


@task.command("list")
@click.option("--limit", default=50, type=click.IntRange(1, MAX_RESULTS), help="Max results")
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
        raise classify_exception(exc) from exc


@task.command("create")
@click.option("--subject", required=True, help="Task subject")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--body", default="", help="Task body")
@click.option("--status", default="NotStarted", help="Initial status")
@click.pass_context
def task_create(ctx, subject, due, body, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        due_date = _parse_due_date(due) if due else None
        account = get_connection(ctx)
        task_obj = _build_task(
            account,
            folder=account.tasks,
            subject=subject,
            body=body,
            status=status,
        )
        if due_date:
            task_obj.due_date = due_date
        task_obj.save()
        formatter.success({"message": "Task created", "id": task_obj.id, "subject": subject})
    except Exception as exc:
        raise classify_exception(exc) from exc


@task.command("update")
@click.argument("task_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--status", default=None, help="New status")
@click.pass_context
def task_update(ctx, task_id, subject, due, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        if all(value is None for value in (subject, due, status)):
            raise CliError(
                "At least one update option is required.",
                code="INVALID_INPUT",
                exit_code=2,
            )
        due_date = _parse_due_date(due) if due is not None else None
        account = get_connection(ctx)
        task_obj = account.tasks.get(id=task_id)
        fields = []
        if subject is not None:
            task_obj.subject = subject
            fields.append("subject")
        if due_date is not None:
            task_obj.due_date = due_date
            fields.append("due_date")
        if status is not None:
            task_obj.status = status
            fields.append("status")
        task_obj.save(update_fields=fields)
        formatter.success({"message": "Task updated", "id": task_id})
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_exception(exc) from exc


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
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_exception(exc) from exc


@task.command("delete")
@click.argument("task_id")
@click.option("--confirm", is_flag=True, help="Confirm permanent deletion")
@click.pass_context
def task_delete(ctx, task_id, confirm):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    require_confirmation(confirm, action="task.delete")
    try:
        account = get_connection(ctx)
        task_obj = account.tasks.get(id=task_id)
        task_obj.delete()
        formatter.success({"message": "Task deleted", "id": task_id, "permanent": True})
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_exception(exc) from exc
