#!/usr/bin/env python3
"""Run an end-to-end write validation matrix against a real Exchange mailbox.

Requires an active Exchange configuration.
Run with:
    python scripts/run_live_write_matrix.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from click.testing import CliRunner  # noqa: E402

from exchange_cli.core.config import ConfigManager  # noqa: E402
from exchange_cli.main import cli  # noqa: E402


def log(msg: str) -> None:
    print(f"[*] {msg}")


def log_pass(msg: str) -> None:
    print(f"[\033[92mPASS\033[0m] {msg}")


def log_fail(msg: str) -> None:
    print(f"[\033[91mFAIL\033[0m] {msg}")


def main() -> int:
    config_dir = os.environ.get("EXCHANGE_CLI_CONFIG")
    cfg = ConfigManager(config_dir=config_dir)
    account_info = cfg.get_account_credentials(None)
    if not account_info:
        print("Error: No Exchange configuration found. Please run 'exchange-cli config init' first.")
        return 1

    my_email = account_info["email"]
    print("==================================================")
    print("Exchange CLI Write Matrix Validation")
    print(f"Target Account: {my_email}")
    print(f"Server: {account_info.get('server')}")
    print("==================================================")

    auto_confirm = os.environ.get("EXCHANGE_LIVE_WRITE_TEST") == "1"
    if not auto_confirm:
        proceed = input("Proceed with live write tests on this mailbox? (y/N): ").strip().lower()
        if proceed != "y":
            print("Aborted.")
            return 0

    runner = CliRunner()
    run_id = uuid.uuid4().hex[:8]
    test_subject = f"[E2E-TEST-{run_id}] Smoke Verification"
    passed = 0
    failed = 0
    failed_steps: list[str] = []

    def step(name: str, args: list[str], input_str: str | None = None) -> dict:
        nonlocal passed, failed
        log(f"Testing {name}: exchange-cli {' '.join(args)}")
        res = runner.invoke(cli, args, input=input_str)
        if res.exit_code != 0:
            log_fail(f"{name} exited with {res.exit_code}: {res.output.strip()}")
            failed += 1
            failed_steps.append(name)
            return {"ok": False, "output": res.output}
        try:
            data = json.loads(res.output)
            if data.get("ok") is False:
                log_fail(f"{name} returned error: {data.get('error')}")
                failed += 1
                failed_steps.append(name)
                return {"ok": False, "data": data}
            log_pass(f"{name} succeeded.")
            passed += 1
            return {"ok": True, "data": data}
        except json.JSONDecodeError:
            log_pass(f"{name} completed with text output.")
            passed += 1
            return {"ok": True, "raw": res.output}

    print("\n--- 1. Task Lifecycle (create, update, complete, delete) ---")
    res = step("task.create", ["task", "create", "--subject", test_subject, "--due", "2026-12-31"])
    task_id = None
    if res.get("ok") and "data" in res and "data" in res["data"]:
        task_id = res["data"]["data"].get("id")

    if task_id:
        step("task.update", ["task", "update", task_id, "--body", "Updated body content"])
        step("task.complete", ["task", "complete", task_id])
        step("task.delete", ["task", "delete", task_id, "--confirm"])

    print("\n--- 2. Draft Lifecycle (create, delete, send) ---")
    draft1_args = [
        "draft", "create",
        "--to", my_email,
        "--subject", f"{test_subject} Draft Delete",
        "--body", "Will be deleted",
    ]
    res = step("draft.create", draft1_args)
    draft1_id = res.get("data", {}).get("data", {}).get("id") if res.get("ok") else None
    if draft1_id:
        step("draft.delete", ["draft", "delete", draft1_id, "--confirm"])

    draft2_args = [
        "draft", "create",
        "--to", my_email,
        "--subject", f"{test_subject} Draft Send",
        "--body", "Will be sent",
    ]
    res = step("draft.create (for send)", draft2_args)
    draft2_id = res.get("data", {}).get("data", {}).get("id") if res.get("ok") else None
    if draft2_id:
        step("draft.send", ["draft", "send", draft2_id, "--confirm"])

    print("\n--- 3. Calendar Lifecycle (create, update, delete) ---")
    cal_create_args = [
        "calendar", "create",
        "--subject", test_subject,
        "--start", "2026-12-31 10:00",
        "--end", "2026-12-31 11:00",
        "--location", "Meeting Room A",
        "--notify", "none",
    ]
    res = step("calendar.create", cal_create_args)
    event_id = res.get("data", {}).get("data", {}).get("id") if res.get("ok") else None
    if event_id:
        step("calendar.update", ["calendar", "update", event_id, "--location", "Meeting Room B", "--notify", "none"])
        step("calendar.delete", ["calendar", "delete", event_id, "--confirm", "--notify", "none"])

    print("\n--- 4. Email Lifecycle (send, read, reply, forward, mark, move, delete) ---")
    body_file = REPO_ROOT / f".test_body_{run_id}.txt"
    body_file.write_text("Hello from exchange-cli automated test.", encoding="utf-8")
    try:
        email_send_args = [
            "email", "send",
            "--to", my_email,
            "--subject", test_subject,
            "--body-file", str(body_file),
            "--confirm",
        ]
        step("email.send", email_send_args)
    finally:
        body_file.unlink(missing_ok=True)

    print("Waiting 5s for delivery to inbox...")
    time.sleep(5)

    res = step("email.list", ["email", "list", "--folder", "inbox", "--limit", "10"])
    found_msg_id = None
    if res.get("ok") and "data" in res.get("data", {}):
        messages = res["data"]["data"]
        for m in messages:
            if m.get("subject") == test_subject:
                found_msg_id = m.get("id")
                break

    if found_msg_id:
        log_pass(f"Found test email in inbox with id: {found_msg_id}")
        step("email.read", ["email", "read", found_msg_id, "--fields", "id,subject,body"])
        step("email.mark-unread", ["email", "mark-unread", found_msg_id])
        step("email.mark-read", ["email", "mark-read", found_msg_id])
        step("email.reply", ["email", "reply", found_msg_id, "--body", "Reply confirmation", "--confirm"])
        fwd_args = ["email", "forward", found_msg_id, "--to", my_email, "--body", "Forward note", "--confirm"]
        step("email.forward", fwd_args)
        step("email.move", ["email", "move", found_msg_id, "--folder", "trash"])
        step("email.delete", ["email", "delete", found_msg_id, "--permanent", "--confirm"])
    else:
        log_fail(f"Could not locate delivered test message with subject: {test_subject}")
        failed += 1

    print("\n==================================================")
    print(f"Summary: {passed} passed, {failed} failed")
    if failed_steps:
        print(f"Failed steps: {', '.join(failed_steps)}")
    print("==================================================")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
