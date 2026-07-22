import queue
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from exchange_cli.core.watch import (
    FolderWatcher,
    _publish_with_gap,
    event_identity,
)


def test_stream_and_backfill_share_new_mail_identity():
    assert event_identity("created", "M1", "CK1") == event_identity(
        "backfill_new_mail", "M1", "CK1"
    )


def test_non_new_events_keep_watermark_in_identity():
    assert event_identity("modified", "M1", "CK1", "W1") != event_identity(
        "modified", "M1", "CK1", "W2"
    )


def test_queue_overflow_emits_gap_before_latest_event():
    subscriber = queue.Queue(maxsize=2)
    subscriber.put({"event_type": "old-1"})
    subscriber.put({"event_type": "old-2"})
    _publish_with_gap(
        subscriber,
        {"event_type": "latest"},
        folder_name="inbox",
        account_email=None,
    )

    assert subscriber.get_nowait()["event_type"] == "watcher_gap"
    assert subscriber.get_nowait()["event_type"] == "latest"


def _watcher(tmp_path, published):
    return FolderWatcher(
        config_dir=tmp_path,
        account_email=None,
        folder_name="inbox",
        backfill_minutes=10,
        publish=published.append,
    )


def test_backfill_uses_server_filter_and_is_not_capped_at_100(tmp_path, monkeypatch):
    published = []
    watcher = _watcher(tmp_path, published)
    now = datetime.now(timezone.utc)
    items = [
        SimpleNamespace(id=f"M{index}", changekey="CK", datetime_received=now)
        for index in range(150)
    ]

    class Query:
        def order_by(self, field):
            assert field == "datetime_received"
            return self

        def __iter__(self):
            return iter(items)

    class Folder:
        def filter(self, **kwargs):
            assert set(kwargs) == {"datetime_received__gte"}
            self.cutoff = kwargs["datetime_received__gte"]
            return Query()

    folder = Folder()
    monkeypatch.setattr(
        "exchange_cli.core.watch.serialize_email_summary",
        lambda item, include_body_preview: {"id": item.id},
    )

    cutoff = now - timedelta(minutes=5)
    watcher._emit_backfill(folder, cutoff)

    assert folder.cutoff == cutoff
    assert len([event for event in published if event["event_type"] == "backfill_new_mail"]) == 150


def test_reconnect_subscribes_before_backfill(tmp_path, monkeypatch):
    published = []
    watcher = _watcher(tmp_path, published)
    actions = []

    class Folder:
        def subscribe_to_streaming(self):
            actions.append("subscribe")
            return "S1"

        def get_streaming_events(self, subscription_id, connection_timeout):
            assert subscription_id == "S1"
            assert connection_timeout == 1
            actions.append("consume")
            watcher.stop()
            return []

        def unsubscribe(self, subscription_id):
            assert subscription_id == "S1"
            actions.append("unsubscribe")

    monkeypatch.setattr(
        watcher,
        "_emit_backfill",
        lambda folder, cutoff: actions.append("backfill"),
    )

    watcher._backfill_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    watcher._run_streaming_once(Folder())

    assert actions == ["subscribe", "backfill", "consume", "unsubscribe"]
    assert watcher._backfill_cutoff is None


def test_backfill_failure_emits_gap_and_exits_subscription_for_retry(tmp_path, monkeypatch):
    published = []
    watcher = _watcher(tmp_path, published)
    actions = []

    class Folder:
        def subscribe_to_streaming(self):
            return "S1"

        def get_streaming_events(self, subscription_id, connection_timeout):
            actions.append("consume")
            return []

        def unsubscribe(self, subscription_id):
            actions.append("unsubscribe")

    def fail_backfill(folder, cutoff):
        raise TimeoutError("backfill timed out")

    monkeypatch.setattr(watcher, "_emit_backfill", fail_backfill)
    watcher._backfill_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    with pytest.raises(TimeoutError, match="backfill timed out"):
        watcher._run_streaming_once(Folder())

    gap = next(event for event in published if event["event_type"] == "watcher_gap")
    assert gap["reason"] == "backfill_failed"
    assert gap["code"] == "TIMEOUT_ERROR"
    assert watcher._backfill_cutoff is not None
    assert actions == ["unsubscribe"]
