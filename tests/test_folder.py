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
    with patch("exchange_cli.commands.folder.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"

        inbox = MagicMock()
        inbox.id = "F1"
        inbox.name = "Inbox"
        inbox.total_count = 150
        inbox.unread_count = 5
        inbox.child_folder_count = 2
        inbox.children = []

        sent = MagicMock()
        sent.id = "F2"
        sent.name = "Sent Items"
        sent.total_count = 300
        sent.unread_count = 0
        sent.child_folder_count = 0
        sent.children = []

        account.root.children = [inbox, sent]
        account.msg_folder_root.children = [inbox, sent]
        mock.return_value = account
        yield account


class TestFolderList:
    def test_list(self, runner, mock_conn):
        result = runner.invoke(cli, ["folder", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestFolderTree:
    def test_tree(self, runner, mock_conn):
        result = runner.invoke(cli, ["folder", "tree"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
