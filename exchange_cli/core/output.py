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

    def error(self, message: str, code: str | None = None, file=None):
        handle = file or sys.stdout
        if self.fmt == "json":
            payload = {"ok": False, "error": message}
            if code:
                payload["code"] = code
            json.dump(payload, handle, ensure_ascii=False)
            handle.write("\n")
            return
        if code:
            handle.write(f"Error [{code}]: {message}\n")
        else:
            handle.write(f"Error: {message}\n")

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
