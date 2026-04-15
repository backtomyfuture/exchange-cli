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
    with patch("exchange_cli.commands.draft.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestDraftList:
    def test_list(self, runner, mock_conn):
        mock_conn.drafts.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["draft", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestDraftCreate:
    def test_create(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["draft", "create", "--to", "a@x.com", "--subject", "Draft", "--body", "WIP"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestDraftSend:
    def test_send(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "send", "D1"])
        assert result.exit_code == 0


class TestDraftDelete:
    def test_delete(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "delete", "D1"])
        assert result.exit_code == 0
