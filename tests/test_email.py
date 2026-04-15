import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from exchange_cli.commands.email import _parse_search_date
from exchange_cli.main import cli


def _mock_message(message_id="AAMk123", subject="Test", is_read=True):
    message = MagicMock()
    message.id = message_id
    message.changekey = "CK1"
    message.subject = subject
    message.sender = MagicMock(name="Sender", email_address="sender@x.com")
    message.sender.name = "Sender"
    message.to_recipients = [MagicMock(name="To", email_address="to@x.com")]
    message.to_recipients[0].name = "To"
    message.cc_recipients = []
    message.bcc_recipients = []
    message.datetime_received = datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc)
    message.datetime_sent = datetime(2024, 7, 15, 10, 29, tzinfo=timezone.utc)
    message.is_read = is_read
    message.has_attachments = False
    message.importance = "Normal"
    message.text_body = "Preview"
    message.body = "<p>Full body</p>"
    message.attachments = []
    return message


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.email.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestEmailList:
    def test_list_inbox(self, runner, mock_conn):
        messages = [_mock_message("M1", "Subject 1"), _mock_message("M2", "Subject 2")]
        mock_conn.inbox.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=messages)
        result = runner.invoke(cli, ["email", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["count"] == 2

    def test_list_with_folder(self, runner, mock_conn):
        mock_conn.sent.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "list", "--folder", "sent"])
        assert result.exit_code == 0

    def test_list_unread(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "list", "--unread"])
        assert result.exit_code == 0


class TestEmailRead:
    def test_read_message(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.inbox.get.return_value = message
        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["subject"] == "Test"
        assert "body" in data["data"]


class TestEmailSend:
    def test_send_basic(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["email", "send", "--to", "a@x.com", "--subject", "Hi", "--body", "Hello"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestEmailSearch:
    def test_search_basic(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "search", "quarterly report"])
        assert result.exit_code == 0

    def test_search_invalid_start_date_returns_invalid_input(self, runner, mock_conn):
        result = runner.invoke(cli, ["email", "search", "quarterly report", "--start", "2024/07/01"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["code"] == "INVALID_INPUT"


class TestEmailSearchDateParsing:
    def test_start_date_without_time_uses_day_start(self):
        parsed = _parse_search_date("2024-07-15", is_end=False)
        assert parsed.year == 2024
        assert parsed.month == 7
        assert parsed.day == 15
        assert parsed.hour == 0
        assert parsed.minute == 0
        assert parsed.second == 0

    def test_end_date_without_time_uses_day_end(self):
        parsed = _parse_search_date("2024-07-15", is_end=True)
        assert parsed.year == 2024
        assert parsed.month == 7
        assert parsed.day == 15
        assert parsed.hour == 23
        assert parsed.minute == 59
        assert parsed.second == 59

    def test_invalid_date_raises_bad_parameter(self):
        with pytest.raises(click.BadParameter):
            _parse_search_date("15-07-2024", is_end=False)
