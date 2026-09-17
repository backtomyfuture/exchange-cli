import json
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from exchange_cli.core.config import ConfigManager
from exchange_cli.main import cli

pytestmark = [
    pytest.mark.live_exchange,
    pytest.mark.skipif(
        os.environ.get("EXCHANGE_LIVE_WRITE_TEST") != "1",
        reason="Set EXCHANGE_LIVE_WRITE_TEST=1 to run mutating Exchange smoke tests",
    ),
]


def test_live_task_lifecycle():
    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    subject = f"[E2E-TEST-{run_id}] Live Task Test"

    res = runner.invoke(cli, ["task", "create", "--subject", subject, "--due", "2026-12-31"])
    if res.exit_code != 0:
        raise AssertionError(res.output or str(res.exception))
    data = json.loads(res.output)
    assert data["ok"] is True
    task_id = data["data"]["id"]

    try:
        res = runner.invoke(cli, ["task", "update", task_id, "--status", "InProgress"])
        if res.exit_code != 0:
            raise AssertionError(res.output or str(res.exception))

        res = runner.invoke(cli, ["task", "complete", task_id])
        assert res.exit_code == 0
    finally:
        res = runner.invoke(cli, ["task", "delete", task_id, "--confirm"])
        assert res.exit_code == 0


def test_live_draft_lifecycle():
    config_dir = os.environ.get("EXCHANGE_CLI_CONFIG")
    cfg = ConfigManager(config_dir=config_dir)
    account_info = cfg.get_account_credentials(None)
    assert account_info, "Active Exchange account required"
    my_email = account_info["email"]

    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    subject = f"[E2E-TEST-{run_id}] Live Draft Test"

    res = runner.invoke(cli, ["draft", "create", "--to", my_email, "--subject", subject, "--body", "Draft content"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] is True
    draft_id = data["data"]["id"]

    try:
        res = runner.invoke(cli, ["draft", "list", "--limit", "10"])
        assert res.exit_code == 0
    finally:
        res = runner.invoke(cli, ["draft", "delete", draft_id, "--confirm"])
        assert res.exit_code == 0


def test_live_calendar_lifecycle():
    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    subject = f"[E2E-TEST-{run_id}] Live Calendar Test"

    res = runner.invoke(
        cli,
        [
            "calendar", "create",
            "--subject", subject,
            "--start", "2026-12-31 10:00",
            "--end", "2026-12-31 11:00",
            "--location", "Room 1",
            "--notify", "none",
        ],
    )
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] is True
    event_id = data["data"]["id"]

    try:
        res = runner.invoke(
            cli,
            [
                "calendar", "update",
                event_id,
                "--location", "Room 2",
                "--notify", "none",
            ],
        )
        assert res.exit_code == 0
    finally:
        res = runner.invoke(cli, ["calendar", "delete", event_id, "--confirm", "--notify", "none"])
        assert res.exit_code == 0


def _ok(result):
    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["ok"] is True, result.output
    return payload


def _account_email():
    config_dir = os.environ.get("EXCHANGE_CLI_CONFIG")
    account_info = ConfigManager(config_dir=config_dir).get_account_credentials(None)
    assert account_info, "Active Exchange account required"
    return account_info["email"]


def test_live_folder_lifecycle():
    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    parent_name = f"E2E-Folder-{run_id}"
    child_name = f"E2E-Child-{run_id}"
    renamed = f"E2E-Child-Renamed-{run_id}"
    parent_id = None
    child_id = None

    try:
        dry = _ok(runner.invoke(cli, ["folder", "create", parent_name, "--dry-run"]))
        assert dry["data"]["preview"]["name"] == parent_name

        created = _ok(runner.invoke(cli, ["folder", "create", parent_name]))
        parent_id = created["data"]["folder"]["id"]

        child = _ok(runner.invoke(cli, ["folder", "create", child_name, "--parent", parent_id]))
        child_id = child["data"]["folder"]["id"]

        renamed_payload = _ok(runner.invoke(cli, ["folder", "rename", child_id, "--name", renamed]))
        assert renamed_payload["data"]["folder"]["name"] == renamed

        blocked = runner.invoke(cli, ["folder", "rename", "inbox", "--name", f"E2E-Inbox-{run_id}"])
        assert blocked.exit_code != 0
        assert json.loads(blocked.output)["code"] in {"INVALID_FOLDER_STATE", "INVALID_FOLDER"}

        moved = _ok(runner.invoke(cli, ["folder", "move", child_id, "--parent", "inbox"]))
        assert moved["data"]["outcome"] == "succeeded"

        emptied = _ok(runner.invoke(cli, ["folder", "empty", parent_id, "--confirm"]))
        assert emptied["data"]["action"] in {"moved_to_deleted_items", "hard_deleted", "soft_deleted"}
    finally:
        if child_id:
            runner.invoke(cli, ["folder", "delete", child_id, "--permanent", "--confirm"])
        if parent_id:
            runner.invoke(cli, ["folder", "delete", parent_id, "--permanent", "--confirm"])


def test_live_draft_attachment_and_email_copy_export():
    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    subject = f"[E2E-TEST-{run_id}] Draft Attach Copy Export"
    my_email = _account_email()
    folder_name = f"E2E-Mail-{run_id}"
    draft_id = None
    folder_id = None
    copied_id = None
    imported_id = None
    mime_imported_id = None

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        attach_path = str(tmp_path / "note.txt")
        inline_path = str(tmp_path / "logo.png")
        export_path = str(tmp_path / "draft.ews")
        mime_path = str(tmp_path / "draft.eml")
        Path(attach_path).write_text("attachment body", encoding="utf-8")
        Path(inline_path).write_bytes(b"\x89PNG\r\n\x1a\n")

        try:
            created = _ok(
                runner.invoke(
                    cli,
                    ["draft", "create", "--to", my_email, "--subject", subject, "--body", "Original body"],
                )
            )
            draft_id = created["data"]["id"]

            updated = _ok(runner.invoke(cli, ["draft", "update", draft_id, "--body", "Updated body"]))
            assert "body" in updated["data"]["updated_fields"]

            attached = _ok(
                runner.invoke(
                    cli,
                    [
                        "draft",
                        "attach",
                        draft_id,
                        "--attach",
                        attach_path,
                        "--inline-attach",
                        f"{inline_path}:logo@e2e",
                    ],
                )
            )
            assert [item["name"] for item in attached["data"]["added"]] == ["note.txt", "logo.png"]
            assert attached["data"]["added"][1]["is_inline"] is True

            detached = _ok(runner.invoke(cli, ["draft", "detach", draft_id, "--name", "note.txt"]))
            assert detached["data"]["removed"][0]["name"] == "note.txt"
            remaining_names = {item["name"] for item in detached["data"]["attachments"]}
            assert "note.txt" not in remaining_names
            assert "logo.png" in remaining_names

            exported = _ok(runner.invoke(cli, ["email", "export", draft_id, "--output", export_path]))
            assert exported["data"]["bytes"] > 0
            mime = _ok(runner.invoke(cli, ["email", "export-mime", draft_id, "--output", mime_path]))
            assert mime["data"]["bytes"] > 0

            folder = _ok(runner.invoke(cli, ["folder", "create", folder_name]))
            folder_id = folder["data"]["folder"]["id"]

            copied = _ok(runner.invoke(cli, ["email", "copy", draft_id, "--folder", folder_id]))
            copied_id = copied["data"]["copied_item"]["id"]
            assert copied_id

            restored = _ok(runner.invoke(cli, ["email", "restore", copied_id, "--folder", folder_id]))
            assert restored["data"]["outcome"] == "succeeded"

            imported = _ok(
                runner.invoke(
                    cli,
                    ["email", "import", "--input", export_path, "--folder", folder_id, "--confirm"],
                )
            )
            imported_id = imported["data"]["imported_item"]["id"]

            mime_imported = _ok(
                runner.invoke(
                    cli,
                    ["email", "import-mime", "--input", mime_path, "--folder", folder_id, "--confirm"],
                )
            )
            mime_imported_id = mime_imported["data"].get("id") or mime_imported["data"].get("imported_item", {}).get(
                "id"
            )

            junk_preview = _ok(runner.invoke(cli, ["email", "mark-junk", draft_id, "--dry-run"]))
            assert junk_preview["data"]["preview"]["requires_confirm"] is True

            archive_preview = _ok(runner.invoke(cli, ["email", "archive", draft_id, "--dry-run"]))
            assert archive_preview["data"]["preview"]["message_id"] == draft_id
        finally:
            for item_id in (mime_imported_id, imported_id, copied_id, draft_id):
                if item_id:
                    runner.invoke(cli, ["email", "delete", item_id, "--permanent", "--confirm"])
            if folder_id:
                runner.invoke(cli, ["folder", "empty", folder_id, "--permanent", "--confirm"])
                runner.invoke(cli, ["folder", "delete", folder_id, "--permanent", "--confirm"])


def test_live_mailbox_rule_lifecycle():
    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    display_name = f"[E2E-TEST-{run_id}] Temporary inbox rule"
    subject_token = f"E2E-RULE-{run_id}-NEVER-MATCH"
    spec_path = None
    rule_id = None

    with tempfile.TemporaryDirectory() as tmp:
        spec_path = str(Path(tmp) / "rule.json")
        with open(spec_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "display_name": display_name,
                    "priority": 50,
                    "is_enabled": False,
                    "conditions": {"contains_subject_strings": [subject_token]},
                    "actions": {"mark_as_read": True, "stop_processing_rules": True},
                },
                handle,
            )

        dry = _ok(runner.invoke(cli, ["mailbox", "rules", "create", "--spec-file", spec_path, "--dry-run"]))
        assert dry["data"]["preview"]["requires_confirm"] is True

        try:
            created = _ok(runner.invoke(cli, ["mailbox", "rules", "create", "--spec-file", spec_path, "--confirm"]))
            rule_id = created["data"]["rule"]["id"]
            assert created["data"]["rule"]["spec"]["display_name"] == display_name

            fetched = _ok(runner.invoke(cli, ["mailbox", "rules", "get", rule_id]))
            assert fetched["data"]["id"] == rule_id

            with open(spec_path, "w", encoding="utf-8") as handle:
                json.dump({"is_enabled": False, "priority": 51}, handle)
            updated = _ok(
                runner.invoke(cli, ["mailbox", "rules", "update", rule_id, "--spec-file", spec_path, "--confirm"])
            )
            assert updated["data"]["rule"]["spec"]["priority"] == 51
        finally:
            if rule_id:
                deleted = _ok(runner.invoke(cli, ["mailbox", "rules", "delete", rule_id, "--confirm"]))
                assert deleted["data"]["outcome"] == "succeeded"



def test_live_high_impact_commands_preview_without_writing():
    runner = CliRunner()
    oof = _ok(
        runner.invoke(
            cli,
            [
                "mailbox",
                "oof",
                "set",
                "--state",
                "disabled",
                "--dry-run",
            ],
        )
    )
    assert oof["data"]["preview"]["requires_confirm"] is True

    meeting = _ok(
        runner.invoke(
            cli,
            ["email", "respond-meeting", "AAMkE2EDryRun", "--response", "decline", "--dry-run"],
        )
    )
    assert meeting["data"]["preview"]["requires_confirm"] is True
