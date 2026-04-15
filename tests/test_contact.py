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
    with patch("exchange_cli.commands.contact.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestContactList:
    def test_list(self, runner, mock_conn):
        mock_conn.contacts.all.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["contact", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestContactSearch:
    def test_search(self, runner, mock_conn):
        mock_conn.contacts.filter.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["contact", "search", "John"])
        assert result.exit_code == 0
