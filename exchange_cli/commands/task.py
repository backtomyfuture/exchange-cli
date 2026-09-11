"""exchange-cli task {list, create, update, complete, delete}."""

from datetime import datetime
from decimal import Decimal

import click
from exchangelib import EWSDate
from exchangelib import Task as EWSTask
from exchangelib.errors import ErrorItemNotFound

from ..core.cli import get_account
from ..core.errors import CliError, classify_exception, classify_write_exception
from ..core.output import OutputFormatter
from ..core.task_service import list_tasks
from ..core.validation import MAX_RESULTS, TASK_STATUSES, normalize_task_status, require_confirmation


def get_connection(ctx):
    return get_account(ctx)


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
@click.option("--status", default=None, type=click.Choice(TASK_STATUSES, case_sensitive=False), help="Filter by status")
@click.pass_context
def task_list(ctx, limit, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        account = get_connection(ctx)
        results, truncated = list_tasks(account, limit=limit, status=status)
        formatter.success(results, count=len(results), truncated=truncated)
    except Exception as exc:
        raise classify_exception(exc) from exc


@task.command("create")
@click.option("--subject", required=True, help="Task subject")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--body", default="", help="Task body")
@click.option(
    "--status",
    default="NotStarted",
    type=click.Choice(TASK_STATUSES, case_sensitive=False),
    help="Initial status",
)
@click.pass_context
def task_create(ctx, subject, due, body, status):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    try:
        due_date = _parse_due_date(due) if due else None
        account = get_connection(ctx)
        task_obj = EWSTask(
            account=account,
            folder=account.tasks,
            subject=subject,
            body=body,
            status=normalize_task_status(status),
        )
        if due_date:
            task_obj.due_date = due_date
        task_obj.save()
        formatter.success({"message": "Task created", "id": task_obj.id, "subject": subject, "outcome": "succeeded"})
    except Exception as exc:
        raise classify_write_exception(exc) from exc


@task.command("update")
@click.argument("task_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--status", default=None, type=click.Choice(TASK_STATUSES, case_sensitive=False), help="New status")
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
            task_obj.status = normalize_task_status(status)
            fields.append("status")
        task_obj.save(update_fields=fields)
        formatter.success({"message": "Task updated", "id": task_id, "outcome": "succeeded"})
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc


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
        formatter.success({"message": "Task completed", "id": task_id, "outcome": "succeeded"})
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc


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
        formatter.success({"message": "Task deleted", "id": task_id, "permanent": True, "outcome": "succeeded"})
    except ErrorItemNotFound as exc:
        raise CliError(f"Task not found: {task_id}", code="NOT_FOUND") from exc
    except Exception as exc:
        raise classify_write_exception(exc) from exc
