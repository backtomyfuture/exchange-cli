import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from exchangelib import FileAttachment
from exchangelib.errors import DoesNotExist, TransportError

from exchange_cli.commands.email import _find_message, _parse_search_date
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

    def test_list_defaults_to_without_preview(self, runner, mock_conn):
        message = _mock_message("M1", "Subject 1")
        mock_conn.inbox.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[message])
        result = runner.invoke(cli, ["email", "list"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"][0]["body_preview"] == ""

    def test_list_with_preview_flag(self, runner, mock_conn):
        message = _mock_message("M1", "Subject 1")
        mock_conn.inbox.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[message])
        result = runner.invoke(cli, ["email", "list", "--with-preview"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"][0]["body_preview"] == "Preview"

    def test_list_rejects_unknown_folder_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "list", "--folder", "unknown"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_list_rejects_excessive_limit_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "list", "--limit", "201"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()


class TestEmailRead:
    def test_find_message_skips_only_not_found(self, mock_conn):
        mock_conn.inbox.get.side_effect = DoesNotExist("missing")
        message = _mock_message()
        mock_conn.sent.get.return_value = message

        assert _find_message(mock_conn, "AAMk123") is message

    def test_find_message_preserves_transport_error(self, mock_conn):
        mock_conn.inbox.get.side_effect = TransportError("offline")

        with pytest.raises(TransportError):
            _find_message(mock_conn, "AAMk123")

    def test_read_message_default_markdown(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello <b>World</b></p></body></html>"
        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["body_format"] == "markdown"
        assert "<html>" not in data["data"]["body"]

    def test_read_message_html_format(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello</p></body></html>"
        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--body-format", "html"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["body_format"] == "html"
        assert "<html>" in data["data"]["body"]

    def test_read_not_found(self, runner, mock_conn):
        with patch("exchange_cli.commands.email._find_message", return_value=None):
            result = runner.invoke(cli, ["email", "read", "NONEXISTENT"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["code"] == "NOT_FOUND"

    def test_read_saves_attachments_and_reports_paths(self, runner, mock_conn, tmp_path):
        message = _mock_message()
        message.attachments = [FileAttachment(name="report.txt", content=b"report")]
        destination = tmp_path / "downloads"

        with patch("exchange_cli.commands.email._find_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "read", "AAMk123", "--save-attachments", str(destination)],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["saved_attachments"] == [str(destination / "report.txt")]
        assert (destination / "report.txt").read_bytes() == b"report"


class TestEmailSend:
    def test_send_basic(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            [
                "email",
                "send",
                "--to",
                "a@x.com",
                "--subject",
                "Hi",
                "--body",
                "Hello",
                "--confirm",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_send_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                ["email", "send", "--to", "a@x.com", "--subject", "Hi", "--body", "Hello"],
            )

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["code"] == "CONFIRMATION_REQUIRED"
        assert payload["details"]["action"] == "email.send"
        get_connection.assert_not_called()

    @pytest.mark.parametrize(
        "args",
        [
            ["email", "reply", "M1", "--body", "Thanks"],
            ["email", "forward", "M1", "--to", "a@x.com"],
        ],
    )
    def test_other_sends_require_confirmation_before_connection(self, runner, args):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, args)

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()


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

    def test_search_rejects_reversed_range_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                [
                    "email",
                    "search",
                    "quarterly report",
                    "--start",
                    "2024-07-31",
                    "--end",
                    "2024-07-01",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_TIME_RANGE"
        get_connection.assert_not_called()


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


class TestEmailWatch:
    def test_watch_runs_in_foreground_and_emits_ndjson(self, runner):
        event = {
            "event_type": "new_mail",
            "timestamp": "2024-07-15T10:30:00+00:00",
            "folder": "inbox",
        }
        with patch("exchange_cli.commands.email.foreground_watch_events", return_value=iter([event])):
            result = runner.invoke(cli, ["email", "watch"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"ok": True, "data": event}
        assert "Watching folder 'inbox'" in result.stderr
