import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from exchangelib.items import HARD_DELETE, MOVE_TO_DELETED_ITEMS, SOFT_DELETE

from exchange_cli.core.errors import CliError
from exchange_cli.core.folder_service import select_folder_delete_type, validate_new_folder_name
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
        assert data["data"][0]["path"] == "Inbox"
        assert data["data"][1]["path"] == "Sent Items"


class TestFolderTree:
    def test_tree(self, runner, mock_conn):
        sub = MagicMock()
        sub.id = "F3"
        sub.name = "Sub"
        sub.total_count = 10
        sub.unread_count = 0
        sub.child_folder_count = 0
        sub.children = []
        mock_conn.msg_folder_root.children[0].children = [sub]

        result = runner.invoke(cli, ["folder", "tree"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        paths = [item["path"] for item in data["data"]]
        assert "Inbox" in paths
        assert "Inbox/Sub" in paths


def _mutable_folder(name="Projects", folder_id="F1"):
    folder = MagicMock()
    folder.id = folder_id
    folder.name = name
    folder.total_count = 0
    folder.unread_count = 0
    folder.child_folder_count = 0
    folder.is_deletable = True
    folder.is_distinguished = False
    folder.DISTINGUISHED_FOLDER_ID = None
    return folder


class TestFolderLifecycle:
    @pytest.mark.parametrize("name", ["", "   ", ".", "..", "parent/child", "parent\\child", "bad\x00name"])
    def test_create_name_rejects_non_single_segments(self, name):
        with pytest.raises(CliError) as caught:
            validate_new_folder_name(name)

        assert caught.value.code == "INVALID_FOLDER"

    def test_folder_name_is_trimmed(self):
        assert validate_new_folder_name("  Projects  ") == "Projects"

    @pytest.mark.parametrize(
        ("permanent", "soft", "expected_type", "expected_action"),
        [
            (False, False, MOVE_TO_DELETED_ITEMS, "moved_to_deleted_items"),
            (True, False, HARD_DELETE, "hard_deleted"),
            (False, True, SOFT_DELETE, "soft_deleted"),
        ],
    )
    def test_select_delete_type(self, permanent, soft, expected_type, expected_action):
        assert select_folder_delete_type(permanent=permanent, soft=soft) == (expected_type, expected_action)

    def test_conflicting_delete_modes_are_rejected_before_connection(self, runner):
        with patch("exchange_cli.commands.folder.get_connection") as get_connection:
            result = runner.invoke(cli, ["folder", "delete", "Projects", "--permanent", "--soft", "--confirm"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_create_calls_folder_helper_with_root_parent(self, runner):
        root = SimpleNamespace(name="Root")
        created = _mutable_folder(name="Projects", folder_id="NEW")
        account = SimpleNamespace(msg_folder_root=root)
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.create_mail_folder", return_value=created) as create_folder,
        ):
            result = runner.invoke(cli, ["folder", "create", "Projects"])

        assert result.exit_code == 0
        create_folder.assert_called_once_with(root, name="Projects")
        data = json.loads(result.output)["data"]
        assert data["folder"]["id"] == "NEW"
        assert data["outcome"] == "succeeded"

    def test_create_dry_run_validates_without_connection(self, runner):
        with patch("exchange_cli.commands.folder.get_connection") as get_connection:
            result = runner.invoke(cli, ["folder", "create", "new/path", "--dry-run"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_FOLDER"
        get_connection.assert_not_called()

    def test_rename_updates_only_name_on_custom_folder(self, runner):
        target = _mutable_folder(name="Old")
        account = MagicMock()
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.resolve_mail_folder", return_value=target),
        ):
            result = runner.invoke(cli, ["folder", "rename", "Old", "--name", "New"])

        assert result.exit_code == 0
        assert target.name == "New"
        target.save.assert_called_once_with(update_fields=["name"])

    def test_rename_blocks_system_folder_even_when_ews_exposes_an_id(self, runner):
        target = _mutable_folder(name="Inbox")
        target.DISTINGUISHED_FOLDER_ID = "inbox"
        account = MagicMock()
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.resolve_mail_folder", return_value=target),
        ):
            result = runner.invoke(cli, ["folder", "rename", "inbox", "--name", "Archive"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_FOLDER_STATE"
        target.save.assert_not_called()

    def test_move_rejects_self_parent_without_structural_mutation(self, runner):
        target = _mutable_folder(folder_id="F1")
        parent = _mutable_folder(name="Projects", folder_id="F1")
        account = MagicMock()
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.resolve_mail_folder", side_effect=[target, parent]),
        ):
            result = runner.invoke(cli, ["folder", "move", "Projects", "--parent", "Projects"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_FOLDER_STATE"
        target.move.assert_not_called()

    def test_delete_requires_confirmation_before_connection(self, runner):
        with patch("exchange_cli.commands.folder.get_connection") as get_connection:
            result = runner.invoke(cli, ["folder", "delete", "Projects"])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()

    def test_delete_permanent_uses_ews_hard_delete(self, runner):
        target = _mutable_folder()
        account = MagicMock()
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.resolve_mail_folder", return_value=target),
        ):
            result = runner.invoke(cli, ["folder", "delete", "Projects", "--permanent", "--confirm"])

        assert result.exit_code == 0
        target.delete.assert_called_once_with(delete_type=HARD_DELETE)
        assert json.loads(result.output)["data"]["action"] == "hard_deleted"

    def test_empty_can_clear_a_system_folder_and_passes_subfolder_mode(self, runner):
        inbox = _mutable_folder(name="Inbox")
        inbox.DISTINGUISHED_FOLDER_ID = "inbox"
        account = MagicMock()
        with (
            patch("exchange_cli.commands.folder.get_connection", return_value=account),
            patch("exchange_cli.commands.folder.resolve_mail_folder", return_value=inbox),
        ):
            result = runner.invoke(
                cli,
                ["folder", "empty", "inbox", "--soft", "--include-subfolders", "--confirm"],
            )

        assert result.exit_code == 0
        inbox.empty.assert_called_once_with(delete_type=SOFT_DELETE, delete_sub_folders=True)
        data = json.loads(result.output)["data"]
        assert data["action"] == "soft_deleted"
        assert data["include_subfolders"] is True
