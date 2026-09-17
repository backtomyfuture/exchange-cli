import json

from exchange_cli.main import cli


def test_dry_run_email_send(runner):
    result = runner.invoke(
        cli,
        [
            "email",
            "send",
            "--to",
            "test@example.com",
            "--subject",
            "Test Subject",
            "--body",
            "Hello World",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "email.send"
    assert data["data"]["preview"]["to"] == ["test@example.com"]
    assert data["data"]["preview"]["subject"] == "Test Subject"
    assert data["data"]["preview"]["body_length"] == 11
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_email_reply(runner):
    result = runner.invoke(
        cli,
        ["email", "reply", "msg-123", "--body", "Reply content", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "email.reply"
    assert data["data"]["preview"]["message_id"] == "msg-123"
    assert data["data"]["preview"]["reply_all"] is False
    assert data["data"]["preview"]["body_length"] == 13
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_email_reply_draft(runner):
    result = runner.invoke(
        cli,
        ["email", "reply", "msg-123", "--body", "Reply content", "--draft", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["preview"]["draft"] is True
    assert data["data"]["preview"]["requires_confirm"] is False


def test_dry_run_email_forward(runner):
    result = runner.invoke(
        cli,
        ["email", "forward", "msg-123", "--to", "forward@example.com", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "email.forward"
    assert data["data"]["preview"]["message_id"] == "msg-123"
    assert data["data"]["preview"]["to"] == ["forward@example.com"]
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_email_forward_draft(runner):
    result = runner.invoke(
        cli,
        ["email", "forward", "msg-123", "--to", "forward@example.com", "--draft", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["preview"]["draft"] is True
    assert data["data"]["preview"]["requires_confirm"] is False


def test_dry_run_email_send_with_inline_attach(runner, tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(b"123")
    result = runner.invoke(
        cli,
        [
            "email",
            "send",
            "--to",
            "a@example.com",
            "--subject",
            "Subj",
            "--body",
            "Body",
            "--inline-attach",
            f"{img}:my-cid",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["preview"]["inline_attachments"][0]["content_id"] == "my-cid"


def test_dry_run_email_delete(runner):
    result = runner.invoke(
        cli,
        ["email", "delete", "msg-123", "--permanent", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "email.delete"
    assert data["data"]["preview"]["message_id"] == "msg-123"
    assert data["data"]["preview"]["permanent"] is True
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_calendar_create(runner):
    result = runner.invoke(
        cli,
        [
            "calendar",
            "create",
            "--subject",
            "Project Sync",
            "--start",
            "2026-09-20 10:00",
            "--end",
            "2026-09-20 11:00",
            "--attendees",
            "alice@example.com, bob@example.com",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "calendar.create"
    assert data["data"]["preview"]["subject"] == "Project Sync"
    assert data["data"]["preview"]["attendees"] == ["alice@example.com", "bob@example.com"]
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_calendar_delete(runner):
    result = runner.invoke(
        cli,
        ["calendar", "delete", "event-999", "--notify", "all", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "calendar.delete"
    assert data["data"]["preview"]["event_id"] == "event-999"
    assert data["data"]["preview"]["notify"] == "all"
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_draft_send(runner):
    result = runner.invoke(
        cli,
        ["draft", "send", "draft-777", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "draft.send"
    assert data["data"]["preview"]["draft_id"] == "draft-777"
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_draft_delete(runner):
    result = runner.invoke(
        cli,
        ["draft", "delete", "draft-777", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "draft.delete"
    assert data["data"]["preview"]["draft_id"] == "draft-777"
    assert data["data"]["preview"]["permanent"] is True
    assert data["data"]["preview"]["requires_confirm"] is True


def test_dry_run_draft_detach(runner):
    result = runner.invoke(
        cli,
        ["draft", "detach", "draft-777", "--attachment-id", "ATT-1", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["action"] == "draft.detach"
    assert data["data"]["preview"]["attachment_ids"] == ["ATT-1"]
    assert data["data"]["preview"]["requires_confirm"] is False


def test_dry_run_task_delete(runner):
    result = runner.invoke(
        cli,
        ["task", "delete", "task-888", "--dry-run"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["data"]["dry_run"] is True
    assert data["data"]["action"] == "task.delete"
    assert data["data"]["preview"]["task_id"] == "task-888"
    assert data["data"]["preview"]["permanent"] is True
    assert data["data"]["preview"]["requires_confirm"] is True
