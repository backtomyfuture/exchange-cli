import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def invoke(runner):
    """Shortcut: invoke(args_list) -> click Result."""

    def _invoke(args, **kwargs):
        return runner.invoke(cli, args, catch_exceptions=False, **kwargs)

    return _invoke


@pytest.fixture
def mock_account():
    """A MagicMock pretending to be an exchangelib Account."""
    account = MagicMock()
    account.primary_smtp_address = "test@example.com"
    account.inbox = MagicMock()
    account.sent = MagicMock()
    account.drafts = MagicMock()
    account.trash = MagicMock()
    account.junk = MagicMock()
    account.calendar = MagicMock()
    account.tasks = MagicMock()
    account.contacts = MagicMock()
    account.root = MagicMock()
    account.msg_folder_root = MagicMock()
    return account


def parse_json(result):
    """Parse JSON from CLI output, assert exit code 0."""
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    return json.loads(result.output)
