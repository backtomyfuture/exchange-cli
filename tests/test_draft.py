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
