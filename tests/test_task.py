import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.task.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestTaskList:
    def test_list(self, runner, mock_conn):
        mock_conn.tasks.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["task", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["truncated"] is False

    def test_list_status_filters_client_side_without_server_filter(self, runner, mock_conn):
        matching = MagicMock(status="NotStarted")
        matching.id = "T1"
        matching.subject = "Open"
        matching.due_date = None
        matching.start_date = None
        matching.complete_date = None
        matching.percent_complete = 0
        matching.importance = "Normal"
        matching.text_body = ""
        other = MagicMock(status="Completed")
        other.id = "T2"
        other.subject = "Done"
        other.due_date = None
        other.start_date = None
        other.complete_date = None
        other.percent_complete = 100
        other.importance = "Normal"
        other.text_body = ""
        mock_conn.tasks.all.return_value.order_by.return_value.__iter__ = lambda self: iter([matching, other])
        mock_conn.tasks.filter.side_effect = AssertionError("status must not be server-filtered")
        result = runner.invoke(cli, ["task", "list", "--status", "NotStarted"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["count"] == 1
        assert payload["data"][0]["id"] == "T1"
        mock_conn.tasks.filter.assert_not_called()


class TestTaskCreate:
    def test_create(self, runner, mock_conn):
        with patch("exchange_cli.commands.task.EWSTask") as task_cls:
            task_obj = MagicMock()
            task_obj.id = "T1"
            task_cls.return_value = task_obj
            result = runner.invoke(cli, ["task", "create", "--subject", "Review PR"])
        assert result.exit_code == 0
        task_obj.save.assert_called_once()

    def test_create_rejects_invalid_due_date_before_connection(self, runner):
        with patch("exchange_cli.commands.task.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                ["task", "create", "--subject", "Review PR", "--due", "2024/07/15"],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()


class TestTaskUpdate:
    def test_update_requires_at_least_one_field_before_connection(self, runner):
        with patch("exchange_cli.commands.task.get_connection") as get_connection:
            result = runner.invoke(cli, ["task", "update", "T1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()


class TestTaskComplete:
    def test_complete(self, runner, mock_conn):
        task = MagicMock()
        task.id = "T1"
        mock_conn.tasks.get.return_value = task
        result = runner.invoke(cli, ["task", "complete", "T1"])
        assert result.exit_code == 0


class TestTaskDelete:
    def test_delete(self, runner, mock_conn):
        task = MagicMock()
        task.id = "T1"
        mock_conn.tasks.get.return_value = task

        result = runner.invoke(cli, ["task", "delete", "T1", "--confirm"])

        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["permanent"] is True

    def test_delete_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.task.get_connection") as get_connection:
            result = runner.invoke(cli, ["task", "delete", "T1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()
