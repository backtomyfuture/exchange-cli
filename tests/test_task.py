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


class TestTaskCreate:
    def test_create(self, runner, mock_conn):
        result = runner.invoke(cli, ["task", "create", "--subject", "Review PR"])
        assert result.exit_code == 0

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
