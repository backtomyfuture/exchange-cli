"""Foreground Exchange streaming watch with reconnect backfill."""

from __future__ import annotations

import queue
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from exchangelib import EWSDateTime

from .config import ConfigManager
from .connection import ConnectionManager
from .email_service import resolve_mail_folder
from .errors import classify_exception
from .serializers import serialize_email_summary
from .validation import MAX_BACKFILL_MINUTES, normalize_folder, validate_bounded_int

MAX_EVENT_BUFFER = 5000


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _camel_to_snake(name: str) -> str:
    out: list[str] = []
    for index, character in enumerate(name):
        if character.isupper() and index > 0 and not name[index - 1].isupper():
            out.append("_")
        out.append(character.lower())
    return "".join(out)


def _safe_item_id(item_id: Any) -> dict[str, Any]:
    if item_id is None:
        return {"id": None, "changekey": None}
    return {"id": getattr(item_id, "id", None), "changekey": getattr(item_id, "changekey", None)}


def event_identity(event_type: str, item_id: Any, changekey: Any, watermark: Any = None) -> str:
    prefix = "new_mail" if event_type in {"new_mail", "created", "backfill_new_mail"} else event_type
    suffix = "" if prefix == "new_mail" else f":{watermark}"
    return f"{prefix}:{item_id}:{changekey}{suffix}"


class FolderWatcher(threading.Thread):
    def __init__(
        self,
        *,
        config_dir: Path,
        account_email: str | None,
        folder_name: str,
        backfill_minutes: int,
        publish,
    ):
        super().__init__(daemon=True)
        self.account_email = account_email
        self.folder_name = folder_name
        self.backfill_minutes = max(backfill_minutes, 1)
        self.publish = publish
        self._stop_event = threading.Event()
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        self._backfill_cutoff: datetime | None = None
        self.connection_manager = ConnectionManager(ConfigManager(config_dir=config_dir))

    def stop(self) -> None:
        self._stop_event.set()

    def _remember(self, event_key: str) -> bool:
        if event_key in self._seen:
            return False
        self._seen.add(event_key)
        self._seen_order.append(event_key)
        while len(self._seen_order) > MAX_EVENT_BUFFER:
            stale = self._seen_order.popleft()
            self._seen.discard(stale)
        return True

    def _emit_status(self, status: str, detail: str | None = None, code: str | None = None) -> None:
        payload = {
            "event_type": "watcher_status",
            "status": status,
            "detail": detail,
            "timestamp": iso_now(),
            "folder": self.folder_name,
            "account": self.account_email,
        }
        if code:
            payload["code"] = code
        self.publish(payload)

    def _emit_gap(self, reason: str, *, detail: str | None = None, code: str | None = None) -> None:
        payload = {
            "event_type": "watcher_gap",
            "reason": reason,
            "detail": detail,
            "timestamp": iso_now(),
            "folder": self.folder_name,
            "account": self.account_email,
        }
        if code:
            payload["code"] = code
        self.publish(payload)

    def _emit_backfill(self, folder, cutoff: datetime) -> None:
        # QuerySet iteration is paginated by exchangelib. Do not slice here: a
        # fixed result cap would silently lose messages in a busy mailbox.
        ews_cutoff = EWSDateTime.from_datetime(cutoff)
        items = folder.filter(datetime_received__gte=ews_cutoff).order_by("datetime_received")
        for item in items:
            received = getattr(item, "datetime_received", None)
            if received is None:
                continue
            received_utc = (
                received.astimezone(timezone.utc)
                if received.tzinfo
                else received.replace(tzinfo=timezone.utc)
            )
            if received_utc < cutoff:
                continue
            event_key = event_identity(
                "backfill_new_mail",
                getattr(item, "id", None),
                getattr(item, "changekey", None),
            )
            if not self._remember(event_key):
                continue
            self.publish(
                {
                    "event_type": "backfill_new_mail",
                    "timestamp": iso_now(),
                    "folder": self.folder_name,
                    "account": self.account_email,
                    "message": serialize_email_summary(item, include_body_preview=False),
                }
            )

    def _emit_notification_events(self, notification, folder) -> None:
        events = getattr(notification, "events", None) or []
        for event in events:
            event_type = _camel_to_snake(event.__class__.__name__.removesuffix("Event"))
            item_info = _safe_item_id(getattr(event, "item_id", None))
            watermark = getattr(event, "watermark", None)
            event_key = event_identity(
                event_type,
                item_info.get("id"),
                item_info.get("changekey"),
                watermark,
            )
            if not self._remember(event_key):
                continue
            payload: dict[str, Any] = {
                "event_type": event_type,
                "timestamp": getattr(event, "timestamp", None).isoformat()
                if getattr(event, "timestamp", None)
                else iso_now(),
                "watermark": watermark,
                "folder": self.folder_name,
                "account": self.account_email,
                "item": item_info,
            }
            if event_type in {"new_mail", "created"} and item_info.get("id"):
                try:
                    message = folder.get(id=item_info["id"])
                    payload["message"] = serialize_email_summary(message, include_body_preview=False)
                except Exception:
                    payload["message"] = {"id": item_info.get("id")}
            self.publish(payload)

    def _run_streaming_once(self, folder) -> None:
        # Establish the replacement subscription first. Messages arriving
        # while backfill runs are then queued by Exchange and deduplicated when
        # streaming consumption resumes.
        subscription_id = folder.subscribe_to_streaming()
        try:
            self._emit_status("streaming_connected")
            if self._backfill_cutoff is not None:
                try:
                    self._emit_backfill(folder, self._backfill_cutoff)
                    self._backfill_cutoff = None
                except Exception as exc:
                    error = classify_exception(exc)
                    self._emit_status("backfill_error", error.message, error.code)
                    self._emit_gap("backfill_failed", detail=error.message, code=error.code)
                    raise
            while not self._stop_event.is_set():
                for notification in folder.get_streaming_events(
                    subscription_id, connection_timeout=1
                ):
                    if self._stop_event.is_set():
                        return
                    self._emit_notification_events(notification, folder)
        finally:
            try:
                folder.unsubscribe(subscription_id)
            except Exception:
                pass

    def run(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                account = self.connection_manager.get_account(self.account_email)
                folder = resolve_mail_folder(account, self.folder_name)
                self._run_streaming_once(folder)
                backoff = 1.0
            except Exception as exc:
                error = classify_exception(exc)
                self._emit_status("streaming_error", error.message, error.code)
                candidate_cutoff = datetime.now(timezone.utc) - timedelta(
                    minutes=self.backfill_minutes
                )
                if self._backfill_cutoff is None or candidate_cutoff < self._backfill_cutoff:
                    self._backfill_cutoff = candidate_cutoff
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 30.0)

def _publish_with_gap(
    target: queue.Queue,
    payload: dict[str, Any],
    *,
    folder_name: str,
    account_email: str | None,
) -> None:
    try:
        target.put_nowait(payload)
        return
    except queue.Full:
        pass

    dropped = 0
    for _ in range(2):
        try:
            target.get_nowait()
            dropped += 1
        except queue.Empty:
            break
    try:
        target.put_nowait(
            {
                "event_type": "watcher_gap",
                "dropped_events": dropped,
                "timestamp": iso_now(),
                "folder": folder_name,
                "account": account_email,
            }
        )
        target.put_nowait(payload)
    except queue.Full:
        pass


def foreground_watch_events(
    config_dir: Path | str | None,
    account_email: str | None,
    folder_name: str,
    backfill_minutes: int,
):
    """Yield watch events in the calling CLI process."""

    config_manager = ConfigManager(config_dir=config_dir)
    config_manager.get_account_credentials(account_email)
    folder_name = normalize_folder(folder_name)
    backfill_minutes = validate_bounded_int(
        backfill_minutes,
        field="backfill_minutes",
        minimum=1,
        maximum=MAX_BACKFILL_MINUTES,
    )
    subscriber: queue.Queue = queue.Queue(maxsize=1024)
    watcher = FolderWatcher(
        config_dir=config_manager.config_dir,
        account_email=account_email,
        folder_name=folder_name,
        backfill_minutes=backfill_minutes,
        publish=lambda payload: _publish_with_gap(
            subscriber,
            payload,
            folder_name=folder_name,
            account_email=account_email,
        ),
    )
    watcher.start()
    try:
        while True:
            try:
                yield subscriber.get(timeout=15)
            except queue.Empty:
                yield {
                    "event_type": "heartbeat",
                    "timestamp": iso_now(),
                    "folder": folder_name,
                    "account": account_email,
                }
    finally:
        watcher.stop()
        watcher.join(timeout=2)
        watcher.connection_manager.close()
