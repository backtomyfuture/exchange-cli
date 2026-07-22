"""Structured errors shared by CLI commands."""

from __future__ import annotations

from typing import Any

import click
from exchangelib.errors import (
    DoesNotExist,
    ErrorAccessDenied,
    ErrorItemNotFound,
    ErrorServerBusy,
    ErrorTimeoutExpired,
    RateLimitError,
    TransportError,
    UnauthorizedError,
)


class CliError(Exception):
    """A safe, machine-readable error intended for CLI consumers."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "SERVER_ERROR",
        exit_code: int = 1,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.retryable = retryable
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": self.message,
            "code": self.code,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def classify_exception(exc: Exception, *, default_code: str = "SERVER_ERROR") -> CliError:
    """Map known exchangelib and local exceptions to the stable CLI contract."""

    if isinstance(exc, CliError):
        return exc
    if isinstance(exc, click.ClickException):
        return CliError(exc.format_message(), code="INVALID_INPUT", exit_code=exc.exit_code)
    if isinstance(exc, UnauthorizedError):
        return CliError("Authentication failed. Check username/password.", code="AUTH_ERROR")
    if isinstance(exc, (DoesNotExist, ErrorItemNotFound)):
        return CliError("The requested Exchange item was not found.", code="NOT_FOUND")
    if isinstance(exc, ErrorAccessDenied):
        return CliError("Exchange denied access to the requested resource.", code="PERMISSION_ERROR")
    if isinstance(exc, (ErrorTimeoutExpired, TimeoutError)):
        return CliError("The Exchange operation timed out.", code="TIMEOUT_ERROR", retryable=True)
    if isinstance(exc, (ErrorServerBusy, RateLimitError)):
        return CliError("Exchange Server is busy. Retry later.", code="SERVER_BUSY", retryable=True)
    if isinstance(exc, TransportError):
        return CliError("Could not connect to Exchange Server.", code="CONNECTION_ERROR", retryable=True)
    if isinstance(exc, (ValueError, TypeError)):
        return CliError(str(exc) or "Invalid input.", code="INVALID_INPUT", exit_code=2)
    return CliError(str(exc) or "Unexpected Exchange Server error.", code=default_code)
