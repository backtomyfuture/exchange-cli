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

    def test_list_paginates_from_the_requested_offset(self, runner, mock_conn):
        drafts = [MagicMock(), MagicMock(), MagicMock()]
        for index, draft in enumerate(drafts, start=1):
            draft.id = f"D{index}"
            draft.changekey = None
            draft.subject = f"Draft {index}"
            draft.sender = None
            draft.to_recipients = []
            draft.cc_recipients = []
            draft.datetime_received = None
            draft.datetime_sent = None
            draft.is_read = False
            draft.has_attachments = False
            draft.importance = "Normal"
            draft.text_body = None
        items_mock = mock_conn.drafts.all.return_value.order_by.return_value
        items_mock.__getitem__.side_effect = lambda item_slice: drafts[item_slice]

        result = runner.invoke(cli, ["draft", "list", "--limit", "1", "--offset", "1"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["offset"] == 1
        assert payload["next_offset"] == 2
        assert payload["data"][0]["id"] == "D2"


class TestDraftCreate:
    def test_create(self, runner, mock_conn):
        with patch("exchange_cli.commands.draft.Message") as message_cls:
            message = MagicMock()
            message.id = "D1"
            message_cls.return_value = message
            result = runner.invoke(
                cli,
                ["draft", "create", "--to", "a@x.com", "--subject", "Draft", "--body", "WIP"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        message.save.assert_called_once()

    def test_create_with_inline_attach(self, runner, mock_conn, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"png data")
        with patch("exchange_cli.commands.draft.Message") as message_cls:
            message = MagicMock()
            message.id = "D1"
            message_cls.return_value = message
            result = runner.invoke(
                cli,
                [
                    "draft",
                    "create",
                    "--to",
                    "a@x.com",
                    "--subject",
                    "Draft",
                    "--body",
                    "WIP",
                    "--inline-attach",
                    f"{img}:custom_cid",
                ],
            )
        assert result.exit_code == 0
        message.attach.assert_called_once()
        att = message.attach.call_args[0][0]
        assert att.name == "img.png"
        assert att.is_inline is True
        assert att.content_id == "custom_cid"

    def test_create_with_from_and_bcc(self, runner, mock_conn):
        with patch("exchange_cli.commands.draft.Message") as message_cls:
            message = MagicMock()
            message.id = "D1"
            message_cls.return_value = message
            result = runner.invoke(
                cli,
                [
                    "draft",
                    "create",
                    "--to",
                    "a@x.com",
                    "--bcc",
                    "bcc@x.com",
                    "--from",
                    "sender@x.com",
                    "--subject",
                    "Draft",
                    "--body",
                    "WIP",
                ],
            )
        assert result.exit_code == 0
        kwargs = message_cls.call_args[1]
        assert kwargs["author"].email_address == "sender@x.com"
        assert kwargs["bcc_recipients"][0].email_address == "bcc@x.com"

    def test_create_sanitizes_html_by_default(self, runner, mock_conn):
        with patch("exchange_cli.commands.draft.Message") as message_cls:
            message = MagicMock()
            message.id = "D1"
            message_cls.return_value = message
            raw_html = '<meta name="ProgId" content="Word.Document"><p>Hello<o:p></o:p></p>'
            result = runner.invoke(
                cli,
                [
                    "draft",
                    "create",
                    "--to",
                    "a@x.com",
                    "--subject",
                    "Draft",
                    "--body",
                    raw_html,
                    "--body-type",
                    "html",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["sanitized"] is True
        assert "word_meta" in data["data"]["sanitized_rules"]
        assert "office_xml_tags" in data["data"]["sanitized_rules"]
        kwargs = message_cls.call_args[1]
        cleaned_body_str = str(kwargs["body"])
        assert "ProgId" not in cleaned_body_str
        assert "<o:p>" not in cleaned_body_str
        assert "<p>Hello</p>" in cleaned_body_str

    def test_create_html_no_sanitize_skips_cleaning(self, runner, mock_conn):
        with patch("exchange_cli.commands.draft.Message") as message_cls:
            message = MagicMock()
            message.id = "D1"
            message_cls.return_value = message
            raw_html = '<meta name="ProgId" content="Word.Document"><p>Hello<o:p></o:p></p>'
            result = runner.invoke(
                cli,
                [
                    "draft",
                    "create",
                    "--to",
                    "a@x.com",
                    "--subject",
                    "Draft",
                    "--body",
                    raw_html,
                    "--body-type",
                    "html",
                    "--no-sanitize",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["sanitized"] is False
        assert "sanitized_rules" not in data["data"]
        kwargs = message_cls.call_args[1]
        cleaned_body_str = str(kwargs["body"])
        assert "ProgId" in cleaned_body_str

    def test_create_dry_run(self, runner, tmp_path):
        img = tmp_path / "img.png"
        img.write_bytes(b"png")
        result = runner.invoke(
            cli,
            [
                "draft",
                "create",
                "--to",
                "a@x.com",
                "--subject",
                "Draft",
                "--body",
                "WIP",
                "--inline-attach",
                str(img),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["dry_run"] is True
        assert data["data"]["preview"]["inline_attachments"][0]["content_id"] == "img.png"


class TestDraftSend:
    def test_send(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "send", "D1", "--confirm"])
        assert result.exit_code == 0

    def test_send_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.draft.get_connection") as get_connection:
            result = runner.invoke(cli, ["draft", "send", "D1"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()


class TestDraftDelete:
    def test_delete(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "delete", "D1", "--confirm"])
        assert result.exit_code == 0
        assert json.loads(result.output)["data"]["permanent"] is True


def _draft_message(draft_id="D1", changekey="CK1"):
    message = MagicMock()
    message.id = draft_id
    message.changekey = changekey
    message.is_draft = True
    message.attachments = []
    return message


class TestDraftAttach:
    def test_attach_adds_regular_and_inline_files(self, runner, mock_conn, tmp_path):
        message = _draft_message()
        regular = tmp_path / "contract.pdf"
        regular.write_bytes(b"pdf")
        inline = tmp_path / "logo.png"
        inline.write_bytes(b"png")

        def _attach(attachment):
            message.attachments.append(attachment)
            attachment.attachment_id = MagicMock(id=f"ATT-{attachment.name}")
            message.changekey = "CK2"

        message.attach.side_effect = _attach

        with patch("exchange_cli.commands.draft.require_draft", return_value=message):
            result = runner.invoke(
                cli,
                [
                    "draft",
                    "attach",
                    "D1",
                    "--attach",
                    str(regular),
                    "--inline-attach",
                    f"{inline}:logo@corp",
                    "--if-changekey",
                    "CK1",
                ],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)["data"]
        assert payload["message"] == "Draft attachments added"
        assert payload["changekey"] == "CK2"
        assert [item["name"] for item in payload["added"]] == ["contract.pdf", "logo.png"]
        assert payload["added"][1]["is_inline"] is True
        assert payload["added"][1]["content_id"] == "logo@corp"
        assert message.attach.call_count == 2

    def test_attach_rejects_non_draft(self, runner, mock_conn):
        message = _draft_message()
        message.is_draft = False
        mock_conn.fetch.return_value = [message]
        result = runner.invoke(cli, ["draft", "attach", "M1", "--attach", __file__])
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "NOT_FOUND"
        message.attach.assert_not_called()

    def test_attach_requires_files(self, runner):
        result = runner.invoke(cli, ["draft", "attach", "D1"])
        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"

    def test_attach_dry_run_does_not_connect(self, runner, tmp_path):
        path = tmp_path / "note.txt"
        path.write_text("hi")
        with patch("exchange_cli.commands.draft.get_connection") as get_connection:
            result = runner.invoke(cli, ["draft", "attach", "D1", "--attach", str(path), "--dry-run"])
        assert result.exit_code == 0
        payload = json.loads(result.output)["data"]
        assert payload["action"] == "draft.attach"
        assert payload["preview"]["attachments"][0]["name"] == "note.txt"
        get_connection.assert_not_called()


class TestDraftDetach:
    def test_detach_by_id_and_unique_name(self, runner, mock_conn):
        message = _draft_message()
        first = MagicMock()
        first.name = "a.txt"
        first.size = 1
        first.content_type = "text/plain"
        first.is_inline = False
        first.content_id = None
        first.attachment_id = MagicMock(id="ATT-A")
        second = MagicMock()
        second.name = "logo.png"
        second.size = 2
        second.content_type = "image/png"
        second.is_inline = True
        second.content_id = "logo"
        second.attachment_id = MagicMock(id="ATT-B")
        message.attachments = [first, second]

        def _detach(attachments):
            for item in attachments:
                message.attachments.remove(item)
            message.changekey = "CK2"

        message.detach.side_effect = _detach

        with patch("exchange_cli.commands.draft.require_draft", return_value=message):
            result = runner.invoke(
                cli,
                ["draft", "detach", "D1", "--attachment-id", "ATT-A", "--name", "logo.png"],
            )

        assert result.exit_code == 0
        payload = json.loads(result.output)["data"]
        assert [item["id"] for item in payload["removed"]] == ["ATT-A", "ATT-B"]
        assert payload["attachments"] == []
        assert payload["changekey"] == "CK2"
        message.detach.assert_called_once()

    def test_detach_rejects_ambiguous_name(self, runner, mock_conn):
        message = _draft_message()
        first = MagicMock(name="dup.txt")
        first.name = "dup.txt"
        first.attachment_id = MagicMock(id="ATT-1")
        second = MagicMock(name="dup.txt")
        second.name = "dup.txt"
        second.attachment_id = MagicMock(id="ATT-2")
        message.attachments = [first, second]

        with patch("exchange_cli.commands.draft.require_draft", return_value=message):
            result = runner.invoke(cli, ["draft", "detach", "D1", "--name", "dup.txt"])

        assert result.exit_code == 2
        payload = json.loads(result.output)
        assert payload["code"] == "INVALID_INPUT"
        message.detach.assert_not_called()

    def test_detach_requires_selector(self, runner):
        result = runner.invoke(cli, ["draft", "detach", "D1"])
        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"

    def test_detach_stale_changekey(self, runner, mock_conn):
        message = _draft_message()
        with patch("exchange_cli.commands.draft.require_draft", return_value=message):
            result = runner.invoke(cli, ["draft", "detach", "D1", "--name", "a.txt", "--if-changekey", "OLD"])
        assert result.exit_code == 1
        assert json.loads(result.output)["code"] == "CONFLICT"
        message.detach.assert_not_called()
