import os

import pytest

from exchange_cli.core.config import ConfigManager
from exchange_cli.core.connection import ConnectionManager
from exchange_cli.core.email_service import list_email_summaries

pytestmark = [
    pytest.mark.live_exchange,
    pytest.mark.skipif(
        os.environ.get("EXCHANGE_LIVE_TEST") != "1",
        reason="Set EXCHANGE_LIVE_TEST=1 to run read-only Exchange smoke tests",
    ),
]


def test_live_connection_and_inbox_summary_shape():
    config_manager = ConfigManager(config_dir=os.environ.get("EXCHANGE_CLI_CONFIG"))
    connection_manager = ConnectionManager(config_manager)
    try:
        account = connection_manager.get_account()
        account.root.refresh()
        results = list_email_summaries(
            account,
            folder_name="inbox",
            limit=1,
            unread=False,
            with_preview=False,
        )
    finally:
        connection_manager.close()

    assert isinstance(results, list)
    assert len(results) <= 1
    if results:
        assert {"id", "subject", "sender", "datetime_received"} <= results[0].keys()
