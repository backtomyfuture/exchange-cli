import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from exchangelib import Folder, HTMLBody
from exchangelib.properties import (
    Actions,
    Conditions,
    DelegatePermissions,
    DelegateUser,
    MailTips,
    RecipientAddress,
    Rule,
    SendingAs,
    UserId,
)

from exchange_cli.core.errors import CliError
from exchange_cli.core.mailbox_service import get_mail_tips
from exchange_cli.main import cli


def _oof_settings():
    return SimpleNamespace(
        state="Scheduled",
        external_audience="Known",
        start=datetime(2099, 1, 1, 9, 0, tzinfo=timezone.utc),
        end=datetime(2099, 1, 1, 17, 0, tzinfo=timezone.utc),
        internal_reply="Internal reply",
        external_reply="External reply",
    )


class TestMailboxOof:
    def test_get_serializes_current_settings(self):
        account = SimpleNamespace(oof_settings=_oof_settings())
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(cli, ["mailbox", "oof", "get"])

        assert result.exit_code == 0
        settings = json.loads(result.output)["data"]
        assert settings == {
            "state": "Scheduled",
            "external_audience": "Known",
            "start": "2099-01-01T09:00:00+00:00",
            "end": "2099-01-01T17:00:00+00:00",
            "internal_reply": "Internal reply",
            "external_reply": "External reply",
        }

    def test_set_builds_html_oof_settings_and_writes_the_account_property(self):
        account = MagicMock()
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(
                cli,
                [
                    "mailbox",
                    "oof",
                    "set",
                    "--state",
                    "scheduled",
                    "--external-audience",
                    "known",
                    "--start",
                    "2099-01-01T09:00:00Z",
                    "--end",
                    "2099-01-01T17:00:00Z",
                    "--internal-reply",
                    "<p>Internal</p>",
                    "--external-reply",
                    "<p>External</p>",
                    "--body-type",
                    "html",
                    "--confirm",
                ],
            )

        assert result.exit_code == 0
        settings = account.oof_settings
        assert settings.state == "Scheduled"
        assert settings.external_audience == "Known"
        assert isinstance(settings.internal_reply, HTMLBody)
        assert str(settings.internal_reply) == "<p>Internal</p>"
        assert settings.start.isoformat() == "2099-01-01T09:00:00+00:00"
        assert json.loads(result.output)["data"]["outcome"] == "succeeded"

    def test_disabled_oof_can_be_set_without_reply_bodies(self):
        account = MagicMock()
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(
                cli,
                ["mailbox", "oof", "set", "--state", "disabled", "--external-audience", "none", "--confirm"],
            )

        assert result.exit_code == 0
        assert account.oof_settings.state == "Disabled"
        assert account.oof_settings.internal_reply is None

    def test_enabled_oof_requires_both_reply_bodies_before_connection(self):
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(
                cli,
                ["mailbox", "oof", "set", "--state", "enabled", "--internal-reply", "Internal"],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_scheduled_oof_requires_a_complete_time_range_before_connection(self):
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(
                cli,
                [
                    "mailbox",
                    "oof",
                    "set",
                    "--state",
                    "scheduled",
                    "--start",
                    "2099-01-01T09:00:00Z",
                    "--internal-reply",
                    "Internal",
                    "--external-reply",
                    "External",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_dry_run_never_connects_or_requires_confirmation(self):
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(
                cli,
                [
                    "mailbox",
                    "oof",
                    "set",
                    "--state",
                    "enabled",
                    "--internal-reply",
                    "Internal",
                    "--external-reply",
                    "External",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        preview = json.loads(result.output)["data"]
        assert preview["dry_run"] is True
        assert preview["preview"]["requires_confirm"] is True
        get_connection.assert_not_called()

    def test_set_requires_confirmation_before_connection(self):
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(
                cli,
                [
                    "mailbox",
                    "oof",
                    "set",
                    "--state",
                    "enabled",
                    "--internal-reply",
                    "Internal",
                    "--external-reply",
                    "External",
                ],
            )

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "CONFIRMATION_REQUIRED"
        get_connection.assert_not_called()


class TestMailboxTips:
    def test_service_uses_sending_as_and_mailbox_recipient_types(self):
        protocol = object()
        account = SimpleNamespace(protocol=protocol, primary_smtp_address="sender@example.com")
        service = MagicMock()
        service.call.return_value = []

        with patch("exchange_cli.core.mailbox_service.GetMailTips", return_value=service) as get_service:
            result = get_mail_tips(
                account,
                recipients=("first@example.com", "second@example.com"),
                sending_as=None,
                requested="MailboxFullStatus",
            )

        assert result == []
        get_service.assert_called_once_with(protocol=protocol)
        kwargs = service.call.call_args.kwargs
        assert isinstance(kwargs["sending_as"], SendingAs)
        assert kwargs["sending_as"].email_address == "sender@example.com"
        assert [recipient.email_address for recipient in kwargs["recipients"]] == [
            "first@example.com",
            "second@example.com",
        ]
        assert kwargs["mail_tips_requested"] == "MailboxFullStatus"

    def test_service_rejects_blank_recipient_before_calling_exchange(self):
        account = SimpleNamespace(protocol=object(), primary_smtp_address="sender@example.com")
        with patch("exchange_cli.core.mailbox_service.GetMailTips") as get_service:
            with pytest.raises(CliError, match="non-empty") as caught:
                get_mail_tips(account, recipients=(" ",), sending_as=None, requested="All")

        assert caught.value.code == "INVALID_INPUT"
        get_service.assert_not_called()

    def test_get_serializes_mail_tip_response(self):
        tip = MailTips(
            recipient_address=RecipientAddress(name="Finance", email_address="finance@example.com"),
            mailbox_full=True,
            total_member_count=4,
            invalid_recipient=False,
        )
        account = SimpleNamespace(primary_smtp_address="sender@example.com")
        with (
            patch("exchange_cli.commands.mailbox.get_connection", return_value=account),
            patch("exchange_cli.commands.mailbox.get_mail_tips", return_value=[tip]) as get_tips,
        ):
            result = CliRunner().invoke(
                cli,
                ["mailbox", "tips", "get", "--to", "finance@example.com", "--request", "mailboxfullstatus"],
            )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["data"][0]["recipient"] == {"name": "Finance", "email": "finance@example.com"}
        assert data["data"][0]["mailbox_full"] is True
        assert data["data"][0]["total_member_count"] == 4
        get_tips.assert_called_once_with(
            account,
            recipients=("finance@example.com",),
            sending_as=None,
            requested="MailboxFullStatus",
        )


class TestMailboxDelegates:
    def test_list_serializes_delegate_permissions(self):
        delegate = DelegateUser(
            user_id=UserId(primary_smtp_address="delegate@example.com", display_name="Delegate User"),
            delegate_permissions=DelegatePermissions(
                inbox_folder_permission_level="Reviewer",
                calendar_folder_permission_level="Editor",
            ),
            receive_copies_of_meeting_messages=True,
            view_private_items=False,
        )
        account = SimpleNamespace(delegates=[delegate])
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(cli, ["mailbox", "delegates", "list"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["count"] == 1
        assert data["data"][0]["user"]["primary_smtp_address"] == "delegate@example.com"
        assert data["data"][0]["permissions"]["inbox_folder_permission_level"] == "Reviewer"
        assert data["data"][0]["permissions"]["calendar_folder_permission_level"] == "Editor"
        assert data["data"][0]["receive_copies_of_meeting_messages"] is True


class TestMailboxRules:
    @staticmethod
    def _write_spec(tmp_path, payload):
        path = tmp_path / "rule.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def _rule(*, rule_id="RULE-1", enabled=True):
        rule = Rule(
            id=rule_id,
            display_name="Existing rule",
            priority=5,
            is_enabled=enabled,
            conditions=Conditions(contains_subject_strings=["old"]),
            actions=Actions(mark_as_read=True, assign_categories=["Existing"]),
        )
        rule.clean()
        return rule

    def test_create_builds_native_rule_and_resolves_folder_action(self, tmp_path):
        spec_path = self._write_spec(
            tmp_path,
            {
                "display_name": "Invoice routing",
                "priority": 3,
                "conditions": {"contains_subject_strings": ["Invoice"]},
                "actions": {
                    "copy_to_folder": {"id": "DEST-ID", "changekey": "DEST-CK"},
                    "forward_to_recipients": ["finance@example.com"],
                    "mark_as_read": True,
                },
            },
        )
        account = MagicMock()
        destination = Folder(id="DEST-ID", changekey="DEST-CK")
        with (
            patch("exchange_cli.commands.mailbox.get_connection", return_value=account),
            patch("exchange_cli.core.email_service.resolve_mail_folder", return_value=destination) as resolve_folder,
        ):
            result = CliRunner().invoke(
                cli,
                ["mailbox", "rules", "create", "--spec-file", str(spec_path), "--confirm"],
            )

        assert result.exit_code == 0
        account.create_rule.assert_called_once()
        created = account.create_rule.call_args.args[0]
        assert created.display_name == "Invoice routing"
        assert created.priority == 3
        assert created.actions.copy_to_folder.folder_id.id == "DEST-ID"
        assert created.actions.copy_to_folder.folder_id.changekey == "DEST-CK"
        forward_recipients = [recipient.email_address for recipient in created.actions.forward_to_recipients]
        assert forward_recipients == ["finance@example.com"]
        assert created.actions.mark_as_read is True
        resolve_folder.assert_called_once_with(account, "DEST-ID")
        output = json.loads(result.output)["data"]
        assert output["outcome"] == "succeeded"
        assert output["rule"]["spec"]["actions"]["copy_to_folder"] == {
            "id": "DEST-ID",
            "changekey": "DEST-CK",
        }

    def test_create_invalid_spec_never_connects(self, tmp_path):
        spec_path = self._write_spec(tmp_path, {"display_name": "Incomplete", "priority": 1})
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(cli, ["mailbox", "rules", "create", "--spec-file", str(spec_path)])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_RULE_SPEC"
        get_connection.assert_not_called()

    def test_create_dry_run_validates_without_connection_or_confirmation(self, tmp_path):
        spec_path = self._write_spec(
            tmp_path,
            {
                "display_name": "Mark receipts",
                "priority": 0,
                "actions": {"mark_as_read": True},
            },
        )
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(
                cli,
                ["mailbox", "rules", "create", "--spec-file", str(spec_path), "--dry-run"],
            )

        assert result.exit_code == 0
        preview = json.loads(result.output)["data"]
        assert preview["preview"]["requires_confirm"] is True
        assert preview["preview"]["spec"]["is_enabled"] is True
        get_connection.assert_not_called()

    def test_update_preserves_omitted_components_and_replaces_actions(self, tmp_path):
        spec_path = self._write_spec(
            tmp_path,
            {
                "display_name": "Updated rule",
                "actions": {"forward_to_recipients": ["new-owner@example.com"]},
            },
        )
        existing = self._rule()
        account = MagicMock()
        account.rules = [existing]
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(
                cli,
                ["mailbox", "rules", "update", "RULE-1", "--spec-file", str(spec_path), "--confirm"],
            )

        assert result.exit_code == 0
        account.set_rule.assert_called_once_with(existing)
        assert existing.display_name == "Updated rule"
        assert existing.priority == 5
        assert existing.conditions.contains_subject_strings == ["old"]
        assert existing.actions.mark_as_read is None
        forward_recipients = [recipient.email_address for recipient in existing.actions.forward_to_recipients]
        assert forward_recipients == ["new-owner@example.com"]

    def test_delete_disabled_rule_applies_upstream_workaround(self):
        disabled = self._rule(enabled=False)
        account = MagicMock()
        account.rules = [disabled]
        calls = []
        account.set_rule.side_effect = lambda rule: calls.append(("set", rule))
        account.delete_rule.side_effect = lambda rule: calls.append(("delete", rule))
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(cli, ["mailbox", "rules", "delete", "RULE-1", "--confirm"])

        assert result.exit_code == 0
        assert [name for name, _ in calls] == ["set", "delete"]
        assert disabled.priority == 10**6
        assert disabled.conditions is None
        assert disabled.exceptions is None
        assert disabled.actions.stop_processing_rules is True

    def test_empty_rule_id_is_rejected_before_connection(self):
        with patch("exchange_cli.commands.mailbox.get_connection") as get_connection:
            result = CliRunner().invoke(cli, ["mailbox", "rules", "get", "  "])

        assert result.exit_code == 2
        assert json.loads(result.output)["code"] == "INVALID_INPUT"
        get_connection.assert_not_called()

    def test_list_returns_reusable_folder_action_specification(self):
        destination = Folder(id="DEST-ID", changekey="DEST-CK")
        rule = Rule(
            id="RULE-2",
            display_name="Move messages",
            priority=1,
            actions=Actions(move_to_folder=destination),
        )
        rule.clean()
        account = SimpleNamespace(rules=[rule])
        with patch("exchange_cli.commands.mailbox.get_connection", return_value=account):
            result = CliRunner().invoke(cli, ["mailbox", "rules", "list"])

        assert result.exit_code == 0
        spec = json.loads(result.output)["data"][0]["spec"]
        assert spec["actions"]["move_to_folder"] == {"id": "DEST-ID", "changekey": "DEST-CK"}
