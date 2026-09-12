import json
import os
import uuid

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
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] is True
    task_id = data["data"]["id"]

    try:
        res = runner.invoke(cli, ["task", "update", task_id, "--body", "Updated body content"])
        assert res.exit_code == 0

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
