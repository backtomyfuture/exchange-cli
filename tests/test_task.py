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


class TestTaskComplete:
    def test_complete(self, runner, mock_conn):
        task = MagicMock()
        task.id = "T1"
        mock_conn.tasks.get.return_value = task
        result = runner.invoke(cli, ["task", "complete", "T1"])
        assert result.exit_code == 0
