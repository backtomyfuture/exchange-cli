import json
import os

import pytest
from click.testing import CliRunner

from exchange_cli.core.config import ConfigManager
from exchange_cli.core.connection import ConnectionManager
from exchange_cli.core.email_service import list_email_summaries
from exchange_cli.main import cli

pytestmark = [
    pytest.mark.live_exchange,
    pytest.mark.skipif(
        os.environ.get("EXCHANGE_LIVE_TEST") != "1",
        reason="Set EXCHANGE_LIVE_TEST=1 to run read-only Exchange smoke tests",
    ),
]


def _invoke(*args):
    result = CliRunner().invoke(cli, list(args))
    payload = json.loads(result.output)
    assert result.exit_code == 0, result.output
    assert payload["ok"] is True
    return payload


def test_live_connection_and_inbox_summary_shape():
    config_manager = ConfigManager(config_dir=os.environ.get("EXCHANGE_CLI_CONFIG"))
    connection_manager = ConnectionManager(config_manager)
    try:
        account = connection_manager.get_account()
        account.root.refresh()
        results, _truncated, _skipped_items, _next_offset = list_email_summaries(
            account,
            folder_name="inbox",
            limit=1,
            offset=0,
            unread=False,
            with_preview=False,
        )
    finally:
        connection_manager.close()

    assert isinstance(results, list)
    assert len(results) <= 1
    if results:
        assert {"id", "subject", "sender", "datetime_received"} <= results[0].keys()


def test_live_mailbox_settings_are_readable():
    config_manager = ConfigManager(config_dir=os.environ.get("EXCHANGE_CLI_CONFIG"))
    email = config_manager.get_account_credentials(None)["email"]

    oof = _invoke("mailbox", "oof", "get")["data"]
    assert oof["state"] in {"Enabled", "Disabled", "Scheduled"}
    assert "internal_reply" in oof
    assert "external_reply" in oof

    tips = _invoke("mailbox", "tips", "get", "--to", email)
    assert tips["count"] == 1
    assert tips["data"][0]["recipient"]["email"].lower() == email.lower()

    delegates = _invoke("mailbox", "delegates", "list")
    assert isinstance(delegates["data"], list)
    assert delegates["count"] == len(delegates["data"])

    rules = _invoke("mailbox", "rules", "list")
    assert isinstance(rules["data"], list)
    if rules["data"]:
        first = rules["data"][0]
        assert first["id"]
        assert "display_name" in first["spec"]
        fetched = _invoke("mailbox", "rules", "get", first["id"])["data"]
        assert fetched["id"] == first["id"]


def test_live_folder_browsing_exposes_paths_and_ids():
    listed = _invoke("folder", "list")
    assert listed["count"] == len(listed["data"])
    assert listed["data"]
    assert {"id", "name"} <= listed["data"][0].keys()

    tree = _invoke("folder", "tree")
    assert tree["count"] == len(tree["data"])
    assert any(node.get("path") for node in tree["data"])
