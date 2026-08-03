"""Output formatting helpers for JSON and text modes."""

import json
import sys
from datetime import date, datetime


def _default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


class OutputFormatter:
    def __init__(self, fmt: str = "json"):
        self.fmt = fmt

    def success(self, data, count: int | None = None, file=None):
        handle = file or sys.stdout
        if self.fmt == "json":
            payload = {"ok": True, "data": data}
            if count is not None:
                payload["count"] = count
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
        file=None,
    ):
        handle = file or sys.stdout
        if self.fmt == "json":
            payload = {"ok": False, "error": message}
            if code:
                payload["code"] = code
            if retryable is not None:
                payload["retryable"] = retryable
            if details:
                payload["details"] = details
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
            payload = {"ok": ok, "data": data}
            if not ok:
                payload["error"] = error or "Doctor checks failed."
                if code:
                    payload["code"] = code
                if retryable is not None:
                    payload["retryable"] = retryable
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
