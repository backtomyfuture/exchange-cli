"""Local daemon for Exchange event watching and lightweight IPC."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import queue
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG_DIR, ConfigManager
from .connection import ConnectionManager
from .serializers import serialize_email_summary

SOCKET_FILENAME = "agent.sock"
PID_FILENAME = "agent.pid"
LOG_FILENAME = "agent.log"
RUNTIME_DIRNAME = "run"
MAX_EVENT_BUFFER = 5000


@dataclass(frozen=True)
class DaemonState:
    config_dir: Path
    runtime_dir: Path
    socket_path: Path
    pid_path: Path
    log_path: Path


def resolve_config_dir(config_path: str | None) -> Path:
    if config_path:
        return Path(config_path).expanduser()
    return DEFAULT_CONFIG_DIR


def build_daemon_state(config_path: str | None) -> DaemonState:
    config_dir = resolve_config_dir(config_path)
    runtime_dir = config_dir / RUNTIME_DIRNAME
    return DaemonState(
        config_dir=config_dir,
        runtime_dir=runtime_dir,
        socket_path=runtime_dir / SOCKET_FILENAME,
        pid_path=runtime_dir / PID_FILENAME,
        log_path=runtime_dir / LOG_FILENAME,
    )


def _write_json_line(handle, payload: dict[str, Any]) -> None:
    handle.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
    handle.flush()


def _read_json_line(handle) -> dict[str, Any] | None:
    line = handle.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


def send_daemon_request(state: DaemonState, payload: dict[str, Any], timeout: float = 3.0) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(state.socket_path))
        with client.makefile("rwb") as handle:
            _write_json_line(handle, payload)
            response = _read_json_line(handle)
            if response is None:
                raise RuntimeError("No response from daemon")
            return response


def iter_daemon_stream(
    state: DaemonState, payload: dict[str, Any], timeout: float = 10.0
) -> tuple[dict[str, Any], Any]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(state.socket_path))
    handle = client.makefile("rwb")
    _write_json_line(handle, payload)
    first_response = _read_json_line(handle)
    if first_response is None:
        handle.close()
        client.close()
        raise RuntimeError("No response from daemon stream")
    return first_response, (client, handle)


def close_daemon_stream(stream_resources: Any) -> None:
    if not stream_resources:
        return
    client, handle = stream_resources
    try:
        handle.close()
    finally:
        client.close()


def daemon_ping(state: DaemonState) -> dict[str, Any] | None:
    try:
        response = send_daemon_request(state, {"action": "ping"}, timeout=1.0)
    except Exception:
        return None
    if not response.get("ok"):
        return None
    return response


def _spawn_daemon_process(state: DaemonState) -> None:
    state.runtime_dir.mkdir(parents=True, exist_ok=True)
    if state.socket_path.exists():
        state.socket_path.unlink(missing_ok=True)
    log_handle = state.log_path.open("a", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "exchange_cli.core.daemon",
        "--serve",
        "--config-dir",
        str(state.config_dir),
    ]
    subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
        close_fds=True,
    )


def start_daemon(state: DaemonState, timeout_seconds: float = 5.0) -> bool:
    if daemon_ping(state):
        return False
    _spawn_daemon_process(state)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if daemon_ping(state):
            return True
        time.sleep(0.2)
    raise RuntimeError("Daemon failed to start within timeout")


def stop_daemon(state: DaemonState) -> bool:
    if not daemon_ping(state):
        return False
    try:
        send_daemon_request(state, {"action": "shutdown"}, timeout=2.0)
    except Exception:
        pid = _read_pid(state.pid_path)
        if pid:
            os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not daemon_ping(state):
            return True
        time.sleep(0.2)
    return False


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _camel_to_snake(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and (not name[i - 1].isupper()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _safe_item_id(item_id: Any) -> dict[str, Any]:
    if item_id is None:
        return {"id": None, "changekey": None}
    return {"id": getattr(item_id, "id", None), "changekey": getattr(item_id, "changekey", None)}


def _resolve_folder(account, folder_name: str):
    mapping = {
        "inbox": account.inbox,
        "sent": account.sent,
        "drafts": account.drafts,
        "trash": account.trash,
        "junk": account.junk,
    }
    return mapping.get(folder_name.lower(), account.inbox)


def _apply_summary_field_projection(queryset, include_body_preview: bool):
    fields = [
        "subject",
        "sender",
        "to_recipients",
        "cc_recipients",
        "datetime_received",
        "datetime_sent",
        "is_read",
        "has_attachments",
        "importance",
    ]
    if include_body_preview:
        fields.append("text_body")
    try:
        return queryset.only(*fields)
    except Exception:
        return queryset


class HybridFolderWatcher(threading.Thread):
    def __init__(
        self,
        *,
        key: tuple[str, str],
        config_dir: Path,
        account_email: str | None,
        folder_name: str,
        backfill_minutes: int,
        publish,
    ):
        super().__init__(daemon=True)
        self.key = key
        self.config_dir = config_dir
        self.account_email = account_email
        self.folder_name = folder_name
        self.backfill_minutes = max(backfill_minutes, 1)
        self.publish = publish
        self._stop_event = threading.Event()
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()
        config_manager = ConfigManager(config_dir=config_dir)
        self.connection_manager = ConnectionManager(config_manager)

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

    def _emit_status(self, status: str, detail: str | None = None) -> None:
        payload = {
            "event_type": "watcher_status",
            "status": status,
            "detail": detail,
            "timestamp": _iso_now(),
            "folder": self.folder_name,
            "account": self.account_email,
        }
        self.publish(self.key, payload)

    def _emit_backfill(self, folder) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.backfill_minutes)
        # Backfill recent messages to compensate transient streaming disconnects.
        items = folder.all().order_by("-datetime_received")[:100]
        for item in reversed(list(items)):
            received = getattr(item, "datetime_received", None)
            if received is None:
                continue
            if received.tzinfo:
                received_utc = received.astimezone(timezone.utc)
            else:
                received_utc = received.replace(tzinfo=timezone.utc)
            if received_utc < cutoff:
                continue
            event_key = f"backfill:{getattr(item, 'id', None)}:{getattr(item, 'changekey', None)}"
            if not self._remember(event_key):
                continue
            self.publish(
                self.key,
                {
                    "event_type": "backfill_new_mail",
                    "timestamp": _iso_now(),
                    "folder": self.folder_name,
                    "account": self.account_email,
                    "message": serialize_email_summary(item, include_body_preview=False),
                },
            )

    def _emit_notification_events(self, notification, folder) -> None:
        events = getattr(notification, "events", None) or []
        for event in events:
            event_class_name = event.__class__.__name__.removesuffix("Event")
            event_type = _camel_to_snake(event_class_name)
            item_info = _safe_item_id(getattr(event, "item_id", None))
            watermark = getattr(event, "watermark", None)
            event_key = f"{event_type}:{item_info.get('id')}:{item_info.get('changekey')}:{watermark}"
            if not self._remember(event_key):
                continue
            payload: dict[str, Any] = {
                "event_type": event_type,
                "timestamp": getattr(event, "timestamp", None).isoformat()
                if getattr(event, "timestamp", None)
                else _iso_now(),
                "watermark": watermark,
                "folder": self.folder_name,
                "account": self.account_email,
                "item": item_info,
            }
            if event_type in {"new_mail", "created"} and item_info.get("id"):
                try:
                    msg = folder.get(id=item_info["id"])
                    payload["message"] = serialize_email_summary(msg, include_body_preview=False)
                except Exception:
                    payload["message"] = {"id": item_info.get("id")}
            self.publish(self.key, payload)

    def _run_streaming_once(self, folder) -> None:
        subscription_id = folder.subscribe_to_streaming()
        try:
            for notification in folder.get_streaming_events(subscription_id, connection_timeout=1):
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
                folder = _resolve_folder(account, self.folder_name)
                self._emit_status("streaming_connected")
                self._run_streaming_once(folder)
                backoff = 1.0
            except Exception as exc:
                self._emit_status("streaming_error", str(exc))
                try:
                    account = self.connection_manager.get_account(self.account_email)
                    folder = _resolve_folder(account, self.folder_name)
                    self._emit_backfill(folder)
                except Exception as backfill_exc:
                    self._emit_status("backfill_error", str(backfill_exc))
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, 30.0)


@dataclass(frozen=True)
class SubscriptionKey:
    account_key: str
    folder_name: str


class WatchManager:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._lock = threading.Lock()
        self._watchers: dict[SubscriptionKey, HybridFolderWatcher] = {}
        self._subscribers: dict[SubscriptionKey, set[queue.Queue]] = {}

    def _publish(self, key: tuple[str, str], payload: dict[str, Any]) -> None:
        subscription_key = SubscriptionKey(*key)
        with self._lock:
            targets = list(self._subscribers.get(subscription_key, set()))
        for target in targets:
            try:
                target.put_nowait(payload)
            except queue.Full:
                try:
                    target.get_nowait()
                except queue.Empty:
                    pass
                try:
                    target.put_nowait(payload)
                except queue.Full:
                    continue

    def subscribe(
        self, account_email: str | None, folder_name: str, backfill_minutes: int
    ) -> tuple[SubscriptionKey, queue.Queue]:
        account_key = account_email or "__default__"
        key = SubscriptionKey(account_key=account_key, folder_name=folder_name.lower())
        q: queue.Queue = queue.Queue(maxsize=1024)
        with self._lock:
            if key not in self._watchers:
                watcher = HybridFolderWatcher(
                    key=(key.account_key, key.folder_name),
                    config_dir=self.config_dir,
                    account_email=account_email,
                    folder_name=folder_name,
                    backfill_minutes=backfill_minutes,
                    publish=self._publish,
                )
                self._watchers[key] = watcher
                self._subscribers[key] = set()
                watcher.start()
            self._subscribers[key].add(q)
        return key, q

    def unsubscribe(self, key: SubscriptionKey, q: queue.Queue) -> None:
        with self._lock:
            subscribers = self._subscribers.get(key)
            if not subscribers:
                return
            subscribers.discard(q)
            if subscribers:
                return
            watcher = self._watchers.pop(key, None)
            self._subscribers.pop(key, None)
        if watcher:
            watcher.stop()

    def shutdown(self) -> None:
        with self._lock:
            watchers = list(self._watchers.values())
            self._watchers.clear()
            self._subscribers.clear()
        for watcher in watchers:
            watcher.stop()


class AgentServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, state: DaemonState):
        self.state = state
        self.config_manager = ConfigManager(config_dir=state.config_dir)
        self.connection_manager = ConnectionManager(self.config_manager)
        self.watch_manager = WatchManager(state.config_dir)
        self.started_at = _iso_now()
        self.shutdown_event = threading.Event()
        if state.socket_path.exists():
            state.socket_path.unlink(missing_ok=True)
        super().__init__(str(state.socket_path), AgentRequestHandler)

    def initiate_shutdown(self) -> None:
        if self.shutdown_event.is_set():
            return
        self.shutdown_event.set()
        threading.Thread(target=self.shutdown, daemon=True).start()


class AgentRequestHandler(socketserver.StreamRequestHandler):
    server: AgentServer

    def _send(self, payload: dict[str, Any]) -> None:
        _write_json_line(self.wfile, payload)

    def handle(self) -> None:
        request = _read_json_line(self.rfile)
        if not request:
            return
        action = request.get("action")
        if action == "ping":
            self._send({"ok": True, "pid": os.getpid(), "started_at": self.server.started_at})
            return
        if action == "shutdown":
            self._send({"ok": True, "message": "Shutting down"})
            self.server.initiate_shutdown()
            return
        if action == "watch":
            self._handle_watch(request)
            return
        if action == "email_list":
            self._handle_email_list(request)
            return
        self._send({"ok": False, "error": f"Unsupported action: {action}"})

    def _handle_watch(self, request: dict[str, Any]) -> None:
        account_email = request.get("account")
        folder_name = request.get("folder", "inbox")
        backfill_minutes = int(request.get("backfill_minutes", 10))
        key, subscriber_q = self.server.watch_manager.subscribe(account_email, folder_name, backfill_minutes)
        self._send(
            {
                "ok": True,
                "type": "subscribed",
                "data": {
                    "account": account_email,
                    "folder": key.folder_name,
                    "backfill_minutes": backfill_minutes,
                },
            }
        )
        try:
            while not self.server.shutdown_event.is_set():
                try:
                    payload = subscriber_q.get(timeout=15)
                except queue.Empty:
                    self._send({"ok": True, "type": "heartbeat", "timestamp": _iso_now()})
                    continue
                self._send({"ok": True, "type": "event", "data": payload})
        except (BrokenPipeError, ConnectionResetError, OSError):
            return
        finally:
            self.server.watch_manager.unsubscribe(key, subscriber_q)

    def _handle_email_list(self, request: dict[str, Any]) -> None:
        account_email = request.get("account")
        folder_name = request.get("folder", "inbox")
        limit = int(request.get("limit", 20))
        unread = bool(request.get("unread", False))
        with_preview = bool(request.get("with_preview", False))
        try:
            account = self.server.connection_manager.get_account(account_email)
            folder = _resolve_folder(account, folder_name)
            queryset = folder.filter(is_read=False) if unread else folder.all()
            projected = _apply_summary_field_projection(queryset, include_body_preview=with_preview)
            items = projected.order_by("-datetime_received")[:limit]
            results = [serialize_email_summary(item, include_body_preview=with_preview) for item in items]
            self._send({"ok": True, "data": results, "count": len(results)})
        except Exception as exc:
            self._send({"ok": False, "error": str(exc)})


def run_daemon_server(config_dir: Path) -> None:
    state = build_daemon_state(str(config_dir))
    state.runtime_dir.mkdir(parents=True, exist_ok=True)
    state.pid_path.write_text(str(os.getpid()), encoding="utf-8")
    server = AgentServer(state)

    def _cleanup() -> None:
        server.watch_manager.shutdown()
        state.socket_path.unlink(missing_ok=True)
        state.pid_path.unlink(missing_ok=True)

    atexit_registered = {"done": False}

    def _do_cleanup() -> None:
        if atexit_registered["done"]:
            return
        atexit_registered["done"] = True
        _cleanup()

    def _handle_signal(_signum, _frame):
        server.initiate_shutdown()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    atexit.register(_do_cleanup)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        _do_cleanup()


def _iter_stream_messages(stream_resources: Any):
    client, handle = stream_resources
    while True:
        try:
            payload = _read_json_line(handle)
        except socket.timeout:
            continue
        if payload is None:
            break
        yield payload
    close_daemon_stream((client, handle))


def stream_watch_events(state: DaemonState, payload: dict[str, Any], timeout: float = 10.0):
    first, resources = iter_daemon_stream(state, payload, timeout=timeout)
    return first, _iter_stream_messages(resources)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="exchange-cli local daemon")
    parser.add_argument("--serve", action="store_true", help="Run daemon server")
    parser.add_argument("--config-dir", default=str(DEFAULT_CONFIG_DIR), help="Config directory path")
    args = parser.parse_args(argv)
    if not args.serve:
        parser.error("--serve is required")
    run_daemon_server(Path(args.config_dir).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
