import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from exchangelib import FileAttachment
from exchangelib.errors import DoesNotExist, TransportError
from exchangelib.properties import ConversationId

from exchange_cli.commands.email import _find_message, _parse_search_date
from exchange_cli.core.errors import CliError
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
    message.unique_body = None
    message.conversation_id = None
    message.message_id = None
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
        mock_conn.inbox.all.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=messages
        )
        result = runner.invoke(cli, ["email", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["count"] == 2
        assert data["truncated"] is False

    def test_list_with_folder(self, runner, mock_conn):
        mock_conn.sent.all.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "list", "--folder", "sent"])
        assert result.exit_code == 0

    def test_list_unread(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[]
        )
        result = runner.invoke(cli, ["email", "list", "--unread"])
        assert result.exit_code == 0

    def test_list_defaults_to_without_preview(self, runner, mock_conn):
        message = _mock_message("M1", "Subject 1")
        mock_conn.inbox.all.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[message]
        )
        result = runner.invoke(cli, ["email", "list"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"][0]["body_preview"] == ""

    def test_list_with_preview_flag(self, runner, mock_conn):
        message = _mock_message("M1", "Subject 1")
        mock_conn.inbox.all.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[message]
        )
        result = runner.invoke(cli, ["email", "list", "--with-preview"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"][0]["body_preview"] == "Preview"

    def test_list_rejects_empty_folder_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "list", "--folder", "   "])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_FOLDER"
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
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["body_format"] == "markdown"
        assert "<html>" not in data["data"]["body"]

    def test_read_message_html_format(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello</p></body></html>"
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--body-format", "html"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["body_format"] == "html"
        assert "<html>" in data["data"]["body"]

    def test_read_returns_minimal_conversation_context(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Full thread body</p></body></html>"
        message.unique_body = "<html><body><p>Current reply only</p></body></html>"
        message.conversation_id = ConversationId(id="AAQkAGconversation", changekey="CK1")
        message.message_id = "<reply-42@example.com>"

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert "body_html" not in data
        assert "unique_body_html" not in data
        assert data["conversation_id"] == "AAQkAGconversation"
        assert data["internet_message_id"] == "<reply-42@example.com>"

    def test_read_with_include_html(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Full thread body</p></body></html>"
        message.unique_body = "<html><body><p>Current reply only</p></body></html>"

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--include-html"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert data["body_html"] == "<html><body><p>Full thread body</p></body></html>"
        assert data["unique_body_html"] == "<html><body><p>Current reply only</p></body></html>"

    def test_read_with_max_body_length(self, runner, mock_conn):
        message = _mock_message()
        message.body = "A" * 200

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--max-body-length", "50"])

        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert len(data["body"]) == 50
        assert data["body_truncated"] is True
        assert data["body_length"] == 200

    def test_read_not_found(self, runner, mock_conn):
        missing = CliError("Message not found: NONEXISTENT", code="NOT_FOUND")
        with patch("exchange_cli.commands.email.require_message", side_effect=missing):
            result = runner.invoke(cli, ["email", "read", "NONEXISTENT"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["code"] == "NOT_FOUND"

    def test_read_saves_attachments_and_reports_paths(self, runner, mock_conn, tmp_path):
        message = _mock_message()
        message.attachments = [FileAttachment(name="report.txt", content=b"report")]
        destination = tmp_path / "downloads"

        with patch("exchange_cli.commands.email.require_message", return_value=message):
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
        with patch("exchange_cli.commands.email.Message") as message_cls:
            message = MagicMock()
            message_cls.return_value = message
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
        assert data["data"]["outcome"] == "succeeded"
        message.send_and_save.assert_called_once()

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

    def test_send_timeout_is_unknown_outcome(self, runner, mock_conn):
        with patch("exchange_cli.commands.email.Message") as message_cls:
            message = MagicMock()
            message.send_and_save.side_effect = TransportError("offline")
            message_cls.return_value = message
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

        payload = json.loads(result.output)
        assert result.exit_code == 1
        assert payload["code"] == "WRITE_OUTCOME_UNKNOWN"
        assert payload["retryable"] is False
        assert payload["outcome"] == "unknown"

    def test_mark_read(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.inbox.get.return_value = message
        result = runner.invoke(cli, ["email", "mark-read", "AAMk123"])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["is_read"] is True
        message.save.assert_called_once()

    def test_move(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.inbox.get.return_value = message
        mock_conn.trash.name = "Deleted Items"
        result = runner.invoke(cli, ["email", "move", "AAMk123", "--folder", "trash"])
        assert result.exit_code == 0
        message.move.assert_called_once_with(mock_conn.trash)

    def test_delete_moves_to_trash_by_default(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.inbox.get.return_value = message
        result = runner.invoke(cli, ["email", "delete", "AAMk123", "--confirm"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["permanent"] is False
        message.move_to_trash.assert_called_once()
        message.delete.assert_not_called()

    def test_delete_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "delete", "AAMk123"])
        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_read_fields_omits_html(self, runner, mock_conn):
        message = _mock_message()
        message.body = "<html><body><p>Hello</p></body></html>"
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "read", "AAMk123", "--fields", "id,subject,body"])
        assert result.exit_code == 0
        data = json.loads(result.output)["data"]
        assert set(data) == {"id", "subject", "body"}
        assert "body_html" not in data


class TestEmailSearch:
    def test_search_basic(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[]
        )
        result = runner.invoke(cli, ["email", "search", "quarterly report"])
        assert result.exit_code == 0

    def test_search_with_advanced_filters(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[]
        )
        result = runner.invoke(
            cli,
            [
                "email",
                "search",
                "quarterly report",
                "--from",
                "alice@example.com",
                "--has-attachments",
                "--start",
                "2024-07-15T10:00:00Z",
                "--end",
                "2024-07-16T18:00:00+08:00",
            ],
        )
        assert result.exit_code == 0
        call_args = mock_conn.inbox.filter.call_args[0]
        q_expr = str(call_args[0])
        assert "sender icontains 'alice@example.com'" in q_expr
        assert "has_attachments == True" in q_expr

    def test_search_criteria_can_serialize_to_xml(self):
        from exchangelib import Folder, Message, Q
        folder = MagicMock(spec=Folder)
        folder.get_item_field_by_fieldname.side_effect = Message.get_field_by_fieldname
        start_dt = _parse_search_date("2026-09-12T00:00:00Z", is_end=False)
        criteria = (
            (Q(subject__icontains="test") | Q(body__icontains="test"))
            & Q(sender__icontains="alice")
            & Q(has_attachments=True)
            & Q(datetime_received__gte=start_dt)
        )
        elem = criteria.to_xml(folders=[folder], version=None, applies_to=None)
        assert elem is not None

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

    def test_rfc3339_utc_date_parsed_correctly(self):
        parsed = _parse_search_date("2024-07-15T10:30:00Z", is_end=False)
        assert parsed.year == 2024
        assert parsed.month == 7
        assert parsed.day == 15
        assert parsed.hour == 10
        assert parsed.minute == 30
        assert str(parsed.tzinfo) == "UTC"

    def test_rfc3339_offset_date_parsed_correctly(self):
        parsed = _parse_search_date("2024-07-15T18:30:00+08:00", is_end=False)
        assert parsed.year == 2024
        assert parsed.month == 7
        assert parsed.day == 15
        assert parsed.hour == 10
        assert parsed.minute == 30
        assert str(parsed.tzinfo) == "UTC"

    def test_invalid_date_raises_bad_parameter(self):
        with pytest.raises(click.BadParameter):
            _parse_search_date("invalid-date-string", is_end=False)


class TestEmailWatch:
    def test_watch_requires_duration_or_forever(self, runner):
        result = runner.invoke(cli, ["email", "watch"])
        assert result.exit_code == 2
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["code"] == "WATCH_DURATION_REQUIRED"

    def test_watch_runs_with_duration_and_emits_ndjson(self, runner):
        event = {
            "event_type": "new_mail",
            "timestamp": "2024-07-15T10:30:00+00:00",
            "folder": "inbox",
        }
        with patch("exchange_cli.commands.email.foreground_watch_events", return_value=iter([event])):
            result = runner.invoke(cli, ["email", "watch", "--duration", "60"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"ok": True, "data": event}
        assert "Watching folder 'inbox'" in result.stderr

    def test_watch_runs_with_forever_and_emits_ndjson(self, runner):
        event = {
            "event_type": "new_mail",
            "timestamp": "2024-07-15T10:30:00+00:00",
            "folder": "inbox",
        }
        with patch("exchange_cli.commands.email.foreground_watch_events", return_value=iter([event])):
            result = runner.invoke(cli, ["email", "watch", "--forever"])

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"ok": True, "data": event}
        assert "Watching folder 'inbox'" in result.stderr
