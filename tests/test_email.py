import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner
from exchangelib import FileAttachment, HTMLBody
from exchangelib.errors import DoesNotExist, TransportError
from exchangelib.items import MeetingRequest
from exchangelib.properties import ConversationId

from exchange_cli.commands.email import _find_message, _parse_search_date
from exchange_cli.core.email_service import scan_email_page
from exchange_cli.core.errors import CliError
from exchange_cli.main import cli


def _mock_message(message_id="AAMk123", subject="Test", is_read=True):
    message = MagicMock()
    message.id = message_id
    message.changekey = "CK1"
    message.subject = subject
    message.item_class = "IPM.Note"
    message.parent_folder_id = None
    message.sender = MagicMock(name="Sender", email_address="sender@x.com")
    message.sender.name = "Sender"
    message.to_recipients = [MagicMock(name="To", email_address="to@x.com")]
    message.to_recipients[0].name = "To"
    message.cc_recipients = []
    message.bcc_recipients = []
    message.datetime_received = datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc)
    message.datetime_sent = datetime(2024, 7, 15, 10, 29, tzinfo=timezone.utc)
    message.is_read = is_read
    message.is_draft = False
    message.has_attachments = False
    message.importance = "Normal"
    message.sensitivity = "Normal"
    message.categories = []
    message.text_body = "Preview"
    message.body = "<p>Full body</p>"
    message.unique_body = None
    message.conversation_id = None
    message.message_id = None
    message.datetime_created = datetime(2024, 7, 15, 10, 0, tzinfo=timezone.utc)
    message.last_modified_time = datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc)
    message.in_reply_to = None
    message.references = None
    message.reply_to = []
    message.headers = {}
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

    def test_list_reports_transport_failure_instead_of_empty_success(self, runner, mock_conn):
        items_mock = mock_conn.inbox.all.return_value.only.return_value.order_by.return_value
        items_mock.__getitem__.side_effect = TransportError("offline")

        result = runner.invoke(cli, ["email", "list"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert payload["code"] == "CONNECTION_ERROR"

    def test_list_returns_a_safe_raw_offset_for_the_next_page(self, runner, mock_conn):
        messages = [_mock_message("M1"), _mock_message("M2"), _mock_message("M3")]
        items_mock = mock_conn.inbox.all.return_value.only.return_value.order_by.return_value
        items_mock.__getitem__.side_effect = lambda item_slice: messages[item_slice]

        result = runner.invoke(cli, ["email", "list", "--limit", "1", "--offset", "1"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["offset"] == 1
        assert payload["next_offset"] == 2
        assert payload["truncated"] is True
        assert [message["id"] for message in payload["data"]] == ["M2"]

    def test_mixed_item_pages_do_not_skip_the_email_after_a_non_email_item(self):
        non_email = object()
        messages = [_mock_message("M1"), _mock_message("M2")]
        items = [non_email, *messages]

        first_page, first_truncated, first_skipped, next_offset = scan_email_page(items, limit=1)
        second_page, second_truncated, second_skipped, final_offset = scan_email_page(
            items, limit=1, offset=next_offset
        )

        assert [message.id for message in first_page] == ["M1"]
        assert first_truncated is True
        assert first_skipped == 1
        assert next_offset == 2
        assert [message.id for message in second_page] == ["M2"]
        assert second_truncated is False
        assert second_skipped == 0
        assert final_offset is None


class TestEmailRead:
    def test_find_message_uses_global_fetch_for_custom_folder_items(self, mock_conn):
        from exchangelib.properties import ItemId

        message = _mock_message("CUSTOM_FOLDER_MESSAGE")
        mock_conn.fetch.return_value = iter([message])

        assert _find_message(mock_conn, "CUSTOM_FOLDER_MESSAGE") is message
        mock_conn.fetch.assert_called_once()
        fetched_ids = mock_conn.fetch.call_args.kwargs["ids"]
        assert len(fetched_ids) == 1
        assert isinstance(fetched_ids[0], ItemId)
        assert fetched_ids[0].id == "CUSTOM_FOLDER_MESSAGE"
        mock_conn.inbox.get.assert_not_called()

    def test_find_message_falls_back_to_folder_scan_when_fetch_returns_not_found(self, mock_conn):
        from exchangelib.errors import ErrorItemNotFound

        mock_conn.fetch.return_value = iter([ErrorItemNotFound("missing")])
        mock_conn.inbox.get.side_effect = DoesNotExist("missing")
        message = _mock_message()
        mock_conn.sent.get.return_value = message

        assert _find_message(mock_conn, "MISSING") is message
        mock_conn.inbox.get.assert_called_once_with(id="MISSING")

    def test_find_message_skips_only_not_found(self, mock_conn):
        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.side_effect = DoesNotExist("missing")
        message = _mock_message()
        mock_conn.sent.get.return_value = message

        assert _find_message(mock_conn, "AAMk123") is message

    def test_find_message_preserves_transport_error(self, mock_conn):
        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.side_effect = TransportError("offline")

        with pytest.raises(TransportError):
            _find_message(mock_conn, "AAMk123")

    def test_find_message_preserves_access_denied_error(self, mock_conn):
        from exchangelib.errors import ErrorAccessDenied

        mock_conn.fetch.return_value = iter([ErrorAccessDenied("denied")])

        with pytest.raises(ErrorAccessDenied):
            _find_message(mock_conn, "AAMk123")

    def test_find_message_skips_invalid_id_malformed(self, mock_conn):
        from exchangelib.errors import ErrorInvalidIdMalformed

        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.side_effect = ErrorInvalidIdMalformed("malformed id")
        message = _mock_message()
        mock_conn.sent.get.return_value = message

        assert _find_message(mock_conn, "AAMkFAKEID") is message

    def test_find_message_falls_back_when_fetch_rejects_slash_containing_ids(self, mock_conn):
        from exchangelib.errors import ErrorInvalidIdMalformed

        slash_id = "AAMkAGFm/PYuYAAA="
        mock_conn.fetch.return_value = iter([ErrorInvalidIdMalformed("Id is malformed.")])
        mock_conn.inbox.get.side_effect = ErrorInvalidIdMalformed("Id is malformed.")
        mock_conn.sent.get.side_effect = ErrorInvalidIdMalformed("Id is malformed.")
        message = _mock_message(slash_id)
        mock_conn.drafts.get.return_value = message

        assert _find_message(mock_conn, slash_id) is message
        mock_conn.drafts.get.assert_called_once_with(id=slash_id)

    def test_read_message_not_found_on_fake_id(self, runner, mock_conn):
        from exchangelib.errors import ErrorInvalidIdMalformed

        mock_conn.fetch.return_value = iter([ErrorInvalidIdMalformed("malformed id")])
        mock_conn.inbox.get.side_effect = ErrorInvalidIdMalformed("malformed id")
        mock_conn.sent.get.side_effect = ErrorInvalidIdMalformed("malformed id")
        mock_conn.drafts.get.side_effect = ErrorInvalidIdMalformed("malformed id")
        mock_conn.trash.get.side_effect = ErrorInvalidIdMalformed("malformed id")
        mock_conn.junk.get.side_effect = ErrorInvalidIdMalformed("malformed id")

        result = runner.invoke(cli, ["email", "read", "AAMkFAKEID"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["code"] == "NOT_FOUND"
        assert data["retryable"] is False

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
        assert data["changekey"] == "CK1"
        assert data["is_draft"] is False
        assert data["headers"] == {}

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


class TestEmailExportImport:
    def test_export_writes_the_opaque_ews_payload_to_a_new_file(self, runner, mock_conn, tmp_path):
        message = _mock_message("M1")
        output_path = tmp_path / "message.ews"
        mock_conn.export.return_value = ["EXPORTED-DATA"]

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "export", "M1", "--output", str(output_path)])

        assert result.exit_code == 0
        assert output_path.read_bytes() == b"EXPORTED-DATA"
        mock_conn.export.assert_called_once_with([message])
        payload = json.loads(result.output)["data"]
        assert payload["format"] == "ews-export"
        assert payload["bytes"] == len(b"EXPORTED-DATA")

    def test_export_never_overwrites_an_existing_local_file(self, runner, mock_conn, tmp_path):
        message = _mock_message("M1")
        output_path = tmp_path / "message.ews"
        output_path.write_bytes(b"keep-me")
        mock_conn.export.return_value = ["EXPORTED-DATA"]

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "export", "M1", "--output", str(output_path)])

        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "OUTPUT_EXISTS"
        assert output_path.read_bytes() == b"keep-me"

    def test_import_uploads_the_exact_ews_payload_to_the_requested_folder(self, runner, mock_conn, tmp_path):
        input_path = tmp_path / "message.ews"
        input_path.write_text("EXPORTED-DATA", encoding="utf-8")
        mock_conn.inbox.name = "Inbox"
        mock_conn.upload.return_value = [("IMPORTED", "CK1")]

        result = runner.invoke(
            cli,
            ["email", "import", "--input", str(input_path), "--folder", "inbox", "--confirm"],
        )

        assert result.exit_code == 0
        mock_conn.upload.assert_called_once_with([(mock_conn.inbox, "EXPORTED-DATA")])
        payload = json.loads(result.output)["data"]
        assert payload["imported_item"] == {"id": "IMPORTED", "changekey": "CK1"}

    def test_import_dry_run_does_not_connect(self, runner, tmp_path):
        input_path = tmp_path / "message.ews"
        input_path.write_text("EXPORTED-DATA", encoding="utf-8")

        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                ["email", "import", "--input", str(input_path), "--folder", "inbox", "--dry-run"],
            )

        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["preview"]["bytes"] == len(b"EXPORTED-DATA")
        get_connection.assert_not_called()

    def test_import_requires_confirmation_before_connecting(self, runner, tmp_path):
        input_path = tmp_path / "message.ews"
        input_path.write_text("EXPORTED-DATA", encoding="utf-8")

        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "import", "--input", str(input_path), "--folder", "inbox"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_export_mime_writes_raw_bytes(self, runner, mock_conn, tmp_path):
        message = _mock_message("M1")
        message.mime_content = b"Subject: Test\r\n\r\nHello"
        output_path = tmp_path / "message.eml"

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "export-mime", "M1", "--output", str(output_path)])

        assert result.exit_code == 0
        assert output_path.read_bytes() == message.mime_content
        assert json.loads(result.output)["data"]["format"] == "rfc822"

    def test_import_mime_creates_a_message_with_the_raw_bytes(self, runner, mock_conn, tmp_path):
        input_path = tmp_path / "message.eml"
        mime_content = b"Subject: Test\r\n\r\nHello"
        input_path.write_bytes(mime_content)
        mock_conn.inbox.name = "Inbox"

        with patch("exchange_cli.commands.email.Message") as message_cls:
            message = MagicMock()
            message.id = "IMPORTED"
            message.changekey = "CK1"
            message_cls.return_value = message
            result = runner.invoke(
                cli,
                ["email", "import-mime", "--input", str(input_path), "--folder", "inbox", "--confirm"],
            )

        assert result.exit_code == 0
        message_cls.assert_called_once_with(account=mock_conn, folder=mock_conn.inbox, mime_content=mime_content)
        message.save.assert_called_once_with()
        assert json.loads(result.output)["data"]["id"] == "IMPORTED"


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

    def test_send_with_inline_attach_and_from(self, runner, mock_conn, tmp_path):
        img = tmp_path / "chart.png"
        img.write_bytes(b"chart png")
        with patch("exchange_cli.commands.email.Message") as message_cls:
            message = MagicMock()
            message_cls.return_value = message
            result = runner.invoke(
                cli,
                [
                    "email",
                    "send",
                    "--to",
                    "target@x.com",
                    "--from",
                    "sender@x.com",
                    "--subject",
                    "With inline image",
                    "--body",
                    '<p><img src="cid:chart@cid"></p>',
                    "--body-type",
                    "html",
                    "--inline-attach",
                    f"{img}:chart@cid",
                    "--confirm",
                ],
            )

        assert result.exit_code == 0
        kwargs = message_cls.call_args[1]
        assert kwargs["author"].email_address == "sender@x.com"
        message.attach.assert_called_once()
        att = message.attach.call_args[0][0]
        assert att.name == "chart.png"
        assert att.is_inline is True
        assert att.content_id == "chart@cid"
        message.send_and_save.assert_called_once()

    def test_reply_send_success(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "reply", "M1", "--body", "Thank you", "--confirm"],
            )

        assert result.exit_code == 0
        message.reply.assert_called_once()
        assert message.reply.call_args[1]["body"] == "Thank you"

    def test_reply_draft_creates_draft_and_returns_id(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        reply_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_REPLY_1"
        reply_item.save.return_value = saved_item
        message.create_reply.return_value = reply_item

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "reply", "M1", "--body", "Draft content", "--draft"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["id"] == "DRAFT_REPLY_1"
        assert data["data"]["original_id"] == "M1"
        message.create_reply.assert_called_once()
        reply_item.save.assert_called_once_with(folder=mock_conn.drafts)

    def test_reply_all_draft(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        reply_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_ALL_1"
        reply_item.save.return_value = saved_item
        message.create_reply_all.return_value = reply_item

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "reply", "M1", "--body", "Draft all", "--all", "--draft"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["id"] == "DRAFT_ALL_1"
        message.create_reply_all.assert_called_once()
        reply_item.save.assert_called_once_with(folder=mock_conn.drafts)

    def test_reply_draft_with_from_and_html(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        reply_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_HTML_1"
        reply_item.save.return_value = saved_item
        message.create_reply.return_value = reply_item

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "reply",
                    "M1",
                    "--body",
                    "<b>Bold</b>",
                    "--body-type",
                    "html",
                    "--from",
                    "alias@x.com",
                    "--draft",
                ],
            )

        assert result.exit_code == 0
        call_kwargs = message.create_reply.call_args[1]
        assert call_kwargs["author"].email_address == "alias@x.com"
        assert isinstance(call_kwargs["body"], HTMLBody)
        reply_item.save.assert_called_once_with(folder=mock_conn.drafts)

    def test_forward_send_success(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "forward", "M1", "--to", "colleague@x.com", "--confirm"],
            )

        assert result.exit_code == 0
        message.forward.assert_called_once()

    def test_forward_draft_creates_draft_and_returns_id(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        forward_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_FWD_1"
        forward_item.save.return_value = saved_item
        message.create_forward.return_value = forward_item

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "forward",
                    "M1",
                    "--to",
                    "colleague@x.com",
                    "--body",
                    "FYI",
                    "--draft",
                ],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["id"] == "DRAFT_FWD_1"
        assert data["data"]["to"] == ["colleague@x.com"]
        forward_item.save.assert_called_once_with(folder=mock_conn.drafts)

    def test_reply_draft_sanitizes_body_by_default(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        reply_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_REPLY_CLEAN"
        reply_item.save.return_value = saved_item
        message.create_reply.return_value = reply_item

        draft_msg = MagicMock()
        draft_msg.body = HTMLBody('<meta name="ProgId" content="Word.Document"><p>Quoted text<o:p></o:p></p>')
        mock_conn.drafts.get.return_value = draft_msg

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "reply", "M1", "--body", "Draft content", "--draft"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["id"] == "DRAFT_REPLY_CLEAN"
        assert data["data"]["sanitized"] is True
        assert "word_meta" in data["data"]["sanitized_rules"]
        mock_conn.drafts.get.assert_called_once_with(id="DRAFT_REPLY_CLEAN")
        draft_msg.save.assert_called_once_with(update_fields=["body"])
        assert "ProgId" not in str(draft_msg.body)
        assert "<o:p>" not in str(draft_msg.body)

    def test_reply_draft_with_no_sanitize(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        reply_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_REPLY_RAW"
        reply_item.save.return_value = saved_item
        message.create_reply.return_value = reply_item

        draft_msg = MagicMock()
        mock_conn.drafts.get.return_value = draft_msg

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "reply", "M1", "--body", "Draft content", "--draft", "--no-sanitize"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["sanitized"] is False
        mock_conn.drafts.get.assert_not_called()
        draft_msg.save.assert_not_called()

    def test_forward_draft_sanitizes_body_by_default(self, runner, mock_conn):
        message = _mock_message("M1", "Original Subject")
        forward_item = MagicMock()
        saved_item = MagicMock()
        saved_item.id = "DRAFT_FWD_CLEAN"
        forward_item.save.return_value = saved_item
        message.create_forward.return_value = forward_item

        draft_msg = MagicMock()
        draft_msg.body = HTMLBody('<link rel="Edit-Time-Data" href="cid:editdata.mso"><p>Quoted<o:p></o:p></p>')
        mock_conn.drafts.get.return_value = draft_msg

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "forward", "M1", "--to", "colleague@x.com", "--draft"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["id"] == "DRAFT_FWD_CLEAN"
        assert data["data"]["sanitized"] is True
        assert "word_links" in data["data"]["sanitized_rules"]
        mock_conn.drafts.get.assert_called_once_with(id="DRAFT_FWD_CLEAN")
        draft_msg.save.assert_called_once_with(update_fields=["body"])
        assert "Edit-Time-Data" not in str(draft_msg.body)

    def test_meeting_response_uses_native_accept_with_optional_proposal(self, runner, mock_conn):
        meeting = MagicMock(spec=MeetingRequest)
        meeting.id = "MEETING1"

        with patch("exchange_cli.commands.email.require_message", return_value=meeting):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "respond-meeting",
                    "MEETING1",
                    "--response",
                    "accept",
                    "--body",
                    "Works for me",
                    "--propose-start",
                    "2026-10-01T09:00:00Z",
                    "--propose-end",
                    "2026-10-01T10:00:00Z",
                    "--confirm",
                ],
            )

        assert result.exit_code == 0
        meeting.accept.assert_called_once()
        kwargs = meeting.accept.call_args.kwargs
        assert kwargs["message_disposition"] == "SendAndSaveCopy"
        assert kwargs["body"] == "Works for me"
        assert kwargs["proposed_start"].isoformat() == "2026-10-01T09:00:00+00:00"
        assert kwargs["proposed_end"].isoformat() == "2026-10-01T10:00:00+00:00"
        assert json.loads(result.output)["data"]["response"] == "accept"

    def test_meeting_response_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "respond-meeting", "MEETING1", "--response", "decline"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_meeting_response_rejects_an_ordinary_message(self, runner, mock_conn):
        message = _mock_message("M1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                ["email", "respond-meeting", "M1", "--response", "tentative", "--confirm"],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_MESSAGE_TYPE"

    def test_meeting_response_requires_both_proposal_bounds_before_connecting(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                [
                    "email",
                    "respond-meeting",
                    "MEETING1",
                    "--response",
                    "tentative",
                    "--propose-start",
                    "2026-10-01T09:00:00Z",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_mark_read(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.return_value = message
        result = runner.invoke(cli, ["email", "mark-read", "AAMk123"])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["is_read"] is True
        message.save.assert_called_once()

    def test_move(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.return_value = message
        mock_conn.trash.name = "Deleted Items"
        result = runner.invoke(cli, ["email", "move", "AAMk123", "--folder", "trash"])
        assert result.exit_code == 0
        message.move.assert_called_once_with(mock_conn.trash)

    def test_delete_moves_to_trash_by_default(self, runner, mock_conn):
        message = _mock_message()
        mock_conn.fetch.side_effect = AttributeError("fetch unsupported")
        mock_conn.inbox.get.return_value = message
        result = runner.invoke(cli, ["email", "delete", "AAMk123", "--confirm"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["permanent"] is False
        message.move_to_trash.assert_called_once()
        message.delete.assert_not_called()

    def test_delete_soft_deletes_to_recoverable_items(self, runner, mock_conn):
        message = _mock_message()
        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "delete", "AAMk123", "--soft", "--confirm"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["soft"] is True
        assert payload["data"]["action"] == "soft_deleted"
        message.soft_delete.assert_called_once()
        message.move_to_trash.assert_not_called()

    def test_delete_rejects_two_delete_modes_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "delete", "AAMk123", "--soft", "--permanent", "--confirm"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

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


class TestEmailUpdate:
    def test_update_draft_replaces_compose_fields_and_uses_changekey_guard(self, runner, mock_conn):
        message = _mock_message("DRAFT1")
        message.is_draft = True

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "update",
                    "DRAFT1",
                    "--subject",
                    "Updated subject",
                    "--body",
                    "<p>Updated body</p>",
                    "--body-type",
                    "html",
                    "--to",
                    "recipient@example.com",
                    "--reply-to",
                    "reply@example.com",
                    "--category",
                    "Finance",
                    "--category",
                    "FY26",
                    "--importance",
                    "high",
                    "--sensitivity",
                    "confidential",
                    "--read-receipt",
                    "--delivery-receipt",
                    "--response-requested",
                    "--if-changekey",
                    "CK1",
                ],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["updated_fields"] == [
            "subject",
            "body",
            "to_recipients",
            "reply_to",
            "categories",
            "importance",
            "sensitivity",
            "is_read_receipt_requested",
            "is_delivery_receipt_requested",
            "is_response_requested",
        ]
        assert message.subject == "Updated subject"
        assert isinstance(message.body, HTMLBody)
        assert message.to_recipients[0].email_address == "recipient@example.com"
        assert message.reply_to[0].email_address == "reply@example.com"
        assert message.categories == ["Finance", "FY26"]
        assert message.importance == "High"
        assert message.sensitivity == "Confidential"
        message.save.assert_called_once_with(
            update_fields=payload["data"]["updated_fields"],
            conflict_resolution="NeverOverwrite",
        )

    def test_update_rejects_draft_only_fields_on_non_draft(self, runner, mock_conn):
        message = _mock_message("M1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "update", "M1", "--to", "recipient@example.com"])

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["code"] == "INVALID_MESSAGE_STATE"
        message.save.assert_not_called()

    def test_update_rejects_stale_changekey_without_saving(self, runner, mock_conn):
        message = _mock_message("M1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "update", "M1", "--subject", "New", "--if-changekey", "OLD"])

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["code"] == "CONFLICT"
        assert payload["details"] == {"expected_changekey": "OLD", "actual_changekey": "CK1"}
        message.save.assert_not_called()

    def test_draft_update_alias_requires_a_draft(self, runner, mock_conn):
        message = _mock_message("M1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["draft", "update", "M1", "--subject", "New"])

        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "NOT_FOUND"
        message.save.assert_not_called()

    def test_update_dry_run_does_not_connect(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(
                cli,
                ["email", "update", "M1", "--clear-categories", "--read", "--dry-run"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["data"]["action"] == "email.update"
        assert payload["data"]["preview"]["updated_fields"] == ["categories", "is_read"]
        get_connection.assert_not_called()

    def test_update_draft_sanitizes_html_body(self, runner, mock_conn):
        message = _mock_message("DRAFT1")
        message.is_draft = True

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "update",
                    "DRAFT1",
                    "--body",
                    '<meta name="ProgId" content="Word.Document"><p>Updated<o:p></o:p></p>',
                    "--body-type",
                    "html",
                ],
            )

        assert result.exit_code == 0
        assert isinstance(message.body, HTMLBody)
        cleaned_body = str(message.body)
        assert "ProgId" not in cleaned_body
        assert "<o:p>" not in cleaned_body
        assert "<p>Updated</p>" in cleaned_body

    def test_update_draft_no_sanitize_preserves_html(self, runner, mock_conn):
        message = _mock_message("DRAFT1")
        message.is_draft = True

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "email",
                    "update",
                    "DRAFT1",
                    "--body",
                    '<meta name="ProgId" content="Word.Document"><p>Updated</p>',
                    "--body-type",
                    "html",
                    "--no-sanitize",
                ],
            )

        assert result.exit_code == 0
        assert isinstance(message.body, HTMLBody)
        assert "ProgId" in str(message.body)


class TestEmailLifecycleOperations:
    def test_copy_uses_the_requested_primary_folder(self, runner, mock_conn):
        message = _mock_message("M1")
        mock_conn.sent.name = "Sent Items"
        message.copy.return_value = ("COPY1", "COPYCK1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "copy", "M1", "--folder", "sent"])

        assert result.exit_code == 0
        message.copy.assert_called_once_with(mock_conn.sent)
        payload = json.loads(result.output)
        assert payload["data"]["copied_item"] == {"id": "COPY1", "changekey": "COPYCK1"}

    def test_archive_targets_the_online_archive_inbox(self, runner, mock_conn):
        message = _mock_message("M1")
        mock_conn.archive_inbox.name = "Archive Inbox"
        message.archive.return_value = True

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "archive", "M1"])

        assert result.exit_code == 0
        message.archive.assert_called_once_with(mock_conn.archive_inbox)
        assert json.loads(result.output)["data"]["folder"] == "Archive Inbox"

    def test_mark_junk_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.email.get_connection") as get_connection:
            result = runner.invoke(cli, ["email", "mark-junk", "M1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_mark_not_junk_uses_upstream_unblock_operation(self, runner, mock_conn):
        message = _mock_message("M1")

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "mark-not-junk", "M1", "--no-move", "--confirm"])

        assert result.exit_code == 0
        message.mark_as_junk.assert_called_once_with(is_junk=False, move_item=False)
        payload = json.loads(result.output)
        assert payload["data"]["is_junk"] is False
        assert payload["data"]["moved"] is False

    def test_restore_reports_the_item_identity_after_move(self, runner, mock_conn):
        message = _mock_message("OLD")
        mock_conn.inbox.name = "Inbox"

        with patch("exchange_cli.commands.email.require_message", return_value=message):
            result = runner.invoke(cli, ["email", "restore", "OLD"])

        assert result.exit_code == 0
        message.move.assert_called_once_with(mock_conn.inbox)
        payload = json.loads(result.output)
        assert payload["data"]["source_id"] == "OLD"
        assert payload["data"]["id"] == "OLD"


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

    def test_search_uses_the_requested_offset(self, runner, mock_conn):
        messages = [_mock_message("M1"), _mock_message("M2"), _mock_message("M3")]
        items_mock = mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value
        items_mock.__getitem__.side_effect = lambda item_slice: messages[item_slice]

        result = runner.invoke(cli, ["email", "search", "quarterly", "--limit", "1", "--offset", "2"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["offset"] == 2
        assert "next_offset" not in payload
        assert [message["id"] for message in payload["data"]] == ["M3"]

    def test_search_resolves_chinese_name_via_directory(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[]
        )
        with patch(
            "exchange_cli.core.contact_service.resolve_directory",
            return_value=([{"name": "张霞", "email": "zhang-xia@tianjin-air.com"}], False),
        ):
            result = runner.invoke(cli, ["email", "search", "通知", "--from", "张霞"])
            assert result.exit_code == 0
            call_args = mock_conn.inbox.filter.call_args[0]
            q_expr = str(call_args[0])
            assert "张霞" in q_expr
            assert "zhang-xia@tianjin-air.com" in q_expr

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


class TestEmailNonMessageHandling:
    def test_list_skips_non_message_items(self, runner, mock_conn):
        contact_item = MagicMock()
        contact_item.id = "C1"
        contact_item.subject = "Not an email"
        del contact_item.sender  # Contacts have no sender attribute

        mail_item = _mock_message("M1", "Real email")

        mock_conn.trash.all.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[contact_item, mail_item]
        )

        result = runner.invoke(cli, ["email", "list", "--folder", "trash"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["count"] == 1
        assert data["data"][0]["id"] == "M1"
        assert data["skipped_items"] == 1


class TestEmailSearchFromResolution:
    def test_search_with_name_containing_spaces(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[_mock_message("M1", "Found")]
        )
        with patch("exchange_cli.core.contact_service.resolve_directory") as mock_resolve:
            mock_resolve.return_value = ([{"name": "zhang-xia", "email": "zhang-xia@example.com"}], False)
            result = runner.invoke(cli, ["email", "search", "test", "--from", "张 霞"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["from_resolved"] is True

    def test_search_with_unresolvable_name_reports_flag(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.only.return_value.order_by.return_value.__getitem__ = MagicMock(
            return_value=[]
        )
        with patch("exchange_cli.core.contact_service.resolve_directory") as mock_resolve:
            mock_resolve.return_value = ([], False)
            result = runner.invoke(cli, ["email", "search", "test", "--from", "不存在的人名"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["from_resolved"] is False


class TestFolderResolution:
    def test_resolve_chinese_folder_names(self):
        from exchange_cli.core.email_service import resolve_mail_folder

        account = MagicMock()
        inbox = MagicMock()
        inbox.name = "收件箱"
        trash = MagicMock()
        trash.name = "已删除邮件"
        account.inbox = inbox
        account.trash = trash

        assert resolve_mail_folder(account, "收件箱") is inbox
        assert resolve_mail_folder(account, "已删除邮件") is trash
        assert resolve_mail_folder(account, "trash") is trash

    def test_resolve_folder_path_with_alias_prefix(self):
        from exchange_cli.core.email_service import resolve_mail_folder

        account = MagicMock()
        inbox = MagicMock()
        sub = MagicMock()
        inbox.__truediv__ = MagicMock(return_value=sub)
        account.inbox = inbox

        assert resolve_mail_folder(account, "inbox/sub") is sub
        assert resolve_mail_folder(account, "收件箱/sub") is sub

    def test_reject_path_traversal_and_dot_paths(self):
        from exchange_cli.core.email_service import resolve_mail_folder
        from exchange_cli.core.errors import CliError

        account = MagicMock()
        inbox = MagicMock()
        account.inbox = inbox

        traversal_cases = [
            "..",
            "../",
            "inbox/../../",
            "inbox/../..",
            "..\\",
            ".",
            "./",
            "inbox/..",
            "收件箱/..",
            "a/../..",
            "/",
            "//",
        ]
        for bad_path in traversal_cases:
            with pytest.raises(CliError) as exc_info:
                resolve_mail_folder(account, bad_path)
            assert exc_info.value.code == "INVALID_FOLDER"
            assert exc_info.value.exit_code == 2

        # inbox/./ should normalize to inbox
        assert resolve_mail_folder(account, "inbox/./") is inbox

    def test_resolve_ews_id_containing_slash(self):
        from exchange_cli.core.email_service import resolve_mail_folder

        account = MagicMock()
        calendar_folder = MagicMock()
        calendar_folder.name = "日历"
        ews_id_with_slash = "AQMkAGFmZTA0NzA3LTI5NTAtNDk3NC05/AAA=" + "A" * 40

        account.root._folders_map = {ews_id_with_slash: calendar_folder}

        assert resolve_mail_folder(account, ews_id_with_slash) is calendar_folder

    def test_resolve_archive_alias_fallback_under_msg_folder_root(self):
        from exchange_cli.core.email_service import resolve_mail_folder

        account = MagicMock(spec=[])  # no archive attribute
        msg_folder_root = MagicMock()
        archive_folder = MagicMock()
        archive_folder.name = "Archive"

        msg_folder_root.__truediv__ = MagicMock(side_effect=lambda name: archive_folder if name == "Archive" else None)
        account.msg_folder_root = msg_folder_root

        assert resolve_mail_folder(account, "归档") is archive_folder
        assert resolve_mail_folder(account, "archive") is archive_folder

    def test_email_search_empty_from_addr_raises_invalid_input(self):
        from click.testing import CliRunner

        from exchange_cli.main import cli

        runner = CliRunner()
        with patch("exchange_cli.commands.email.get_account") as mock_get_acc:
            account = MagicMock()
            mock_get_acc.return_value = account
            result = runner.invoke(cli, ["email", "search", "test", "--from", ""])
            assert result.exit_code == 2
            data = json.loads(result.output)
            assert data["ok"] is False
            assert data["code"] == "INVALID_INPUT"

            result_whitespace = runner.invoke(cli, ["email", "search", "test", "--from", "   "])
            assert result_whitespace.exit_code == 2
            data_ws = json.loads(result_whitespace.output)
            assert data_ws["ok"] is False
            assert data_ws["code"] == "INVALID_INPUT"

    def test_email_watch_invalid_folder_does_not_echo_banner(self):
        from click.testing import CliRunner

        from exchange_cli.main import cli

        runner = CliRunner()
        with patch("exchange_cli.commands.email.get_account") as mock_get_acc:
            account = MagicMock()
            mock_get_acc.return_value = account
            result = runner.invoke(cli, ["email", "watch", "--folder", "..", "--duration", "3"])
            assert result.exit_code == 2
            assert "Watching folder" not in result.stderr
            data = json.loads(result.stdout)
            assert data["ok"] is False
            assert data["code"] == "INVALID_FOLDER"
