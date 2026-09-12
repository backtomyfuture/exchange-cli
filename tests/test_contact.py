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
        mock_conn.contacts.all.return_value.__iter__ = lambda self: iter([])
        result = runner.invoke(cli, ["contact", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestContactSearch:
    def test_search(self, runner, mock_conn):
        mock_conn.contacts.filter.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["contact", "search", "John"])
        assert result.exit_code == 0


class TestContactResolve:
    def test_resolve_uses_directory(self, runner, mock_conn):
        mailbox = MagicMock()
        mailbox.name = "Zhang San"
        mailbox.email_address = "zhang.san@example.com"
        mailbox.mailbox_type = "Mailbox"
        contact = MagicMock(display_name="Zhang San", job_title="Engineer", department="IT", company_name="Acme")
        mock_conn.protocol.config.version = None
        mock_conn.protocol.version = MagicMock(api_version="Exchange2016")
        mock_conn.protocol.resolve_names.return_value = [(mailbox, contact)]
        result = runner.invoke(cli, ["contact", "resolve", "张三"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"][0]["email"] == "zhang.san@example.com"
        assert payload["data"][0]["source"] == "directory"
        mock_conn.protocol.resolve_names.assert_called_once()
        assert mock_conn.protocol.version.api_version == "Exchange2016"
