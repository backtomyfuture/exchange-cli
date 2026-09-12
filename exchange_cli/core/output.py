"""Output formatting helpers for JSON and text modes."""

import contextvars
import json
import sys
import time
from datetime import date, datetime
from typing import Any

_current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_request_id", default=None)
_current_start_time: contextvars.ContextVar[float | None] = contextvars.ContextVar("current_start_time", default=None)


def set_current_request_context(request_id: str | None, start_time: float | None = None) -> None:
    _current_request_id.set(request_id)
    _current_start_time.set(start_time)


def _default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


class OutputFormatter:
    def __init__(
        self,
        fmt: str = "json",
        request_id: str | None = None,
        start_time: float | None = None,
    ):
        self.fmt = fmt
        self.request_id = request_id or _current_request_id.get()
        self.start_time = start_time if start_time is not None else _current_start_time.get()

    @classmethod
    def from_context(cls, ctx=None) -> "OutputFormatter":
        if ctx is None or not getattr(ctx, "obj", None):
            return cls()
        return cls(
            fmt=ctx.obj.get("fmt", "json"),
            request_id=ctx.obj.get("request_id"),
            start_time=ctx.obj.get("start_time"),
        )

    def success(
        self,
        data,
        count: int | None = None,
        truncated: bool | None = None,
        skipped_items: int | None = None,
        from_resolved: bool | None = None,
        file=None,
    ):
        handle = file or sys.stdout
        if self.fmt == "json":
            payload: dict[str, Any] = {"ok": True, "data": data}
            if count is not None:
                payload["count"] = count
            if truncated is not None:
                payload["truncated"] = truncated
            if skipped_items is not None and skipped_items > 0:
                payload["skipped_items"] = skipped_items
            if from_resolved is not None:
                payload["from_resolved"] = from_resolved
            if self.request_id:
                meta: dict[str, Any] = {"request_id": self.request_id}
                if self.start_time is not None:
                    meta["elapsed_ms"] = round((time.monotonic() - self.start_time) * 1000, 2)
                payload["meta"] = meta
            json.dump(payload, handle, ensure_ascii=False, default=_default_serializer)
            handle.write("\n")
            return
        self._print_text(data, handle)

    def error(
        self,
        message: str,
        code: str | None = None,
        *,
        retryable: bool | None = None,
        details: dict | None = None,
        outcome: str | None = None,
        file=None,
    ):
        handle = file or (sys.stdout if self.fmt == "json" else sys.stderr)
        if self.fmt == "json":
            payload: dict[str, Any] = {"ok": False, "error": message}
            if code:
                payload["code"] = code
            if retryable is not None:
                payload["retryable"] = retryable
            if outcome:
                payload["outcome"] = outcome
            if details:
                payload["details"] = details
            if self.request_id:
                payload["request_id"] = self.request_id
                meta: dict[str, Any] = {"request_id": self.request_id}
                if self.start_time is not None:
                    meta["elapsed_ms"] = round((time.monotonic() - self.start_time) * 1000, 2)
                payload["meta"] = meta
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
            return
        if code:
            handle.write(f"Error [{code}]: {message}\n")
        else:
            handle.write(f"Error: {message}\n")

    def diagnostic(
        self,
        data: dict,
        *,
        ok: bool = True,
        error: str | None = None,
        code: str | None = None,
        retryable: bool | None = None,
        file=None,
    ):
        """Render a diagnostic report while preserving checks on failure."""

        handle = file or sys.stdout
        if self.fmt == "json":
            payload: dict[str, Any] = {"ok": ok, "data": data}
            if not ok:
                payload["error"] = error or "Doctor checks failed."
                if code:
                    payload["code"] = code
                payload["retryable"] = retryable if retryable is not None else False
                if self.request_id:
                    payload["request_id"] = self.request_id
            if self.request_id:
                meta: dict[str, Any] = {"request_id": self.request_id}
                if self.start_time is not None:
                    meta["elapsed_ms"] = round((time.monotonic() - self.start_time) * 1000, 2)
                payload["meta"] = meta
            json.dump(payload, handle, ensure_ascii=False, default=_default_serializer)
            handle.write("\n")
            return

        overall = str(data.get("overall", "unknown")).upper()
        handle.write(f"Doctor: {overall}\n")
        for check in data.get("checks", []):
            status = str(check.get("status", "unknown")).upper()
            check_id = check.get("id", "unknown")
            message = check.get("message")
            check_code = check.get("code")
            suffix = f" [{check_code}]" if check_code else ""
            detail = f": {message}" if message else ""
            handle.write(f"{status} {check_id}{suffix}{detail}\n")
            remediation = check.get("remediation")
            if remediation:
                handle.write(f"  Fix: {remediation}\n")

        if not ok and error:
            self.error(error, code=code, retryable=retryable, file=handle)

    def _print_text(self, data, handle):
        if isinstance(data, list):
            if not data:
                handle.write("(no results)\n")
                return
            keys = list(data[0].keys())
            header = "  ".join(key.ljust(20) for key in keys)
            handle.write(header + "\n")
            handle.write("-" * len(header) + "\n")
            for row in data:
                line = "  ".join(str(row.get(key, "")).ljust(20) for key in keys)
                handle.write(line + "\n")
            return
        if isinstance(data, dict):
            for key, value in data.items():
                handle.write(f"{key}: {value}\n")
            return
        handle.write(f"{data}\n")
