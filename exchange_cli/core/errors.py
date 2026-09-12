"""Structured errors shared by CLI commands."""

from __future__ import annotations

from typing import Any

import click
from exchangelib.errors import (
    DoesNotExist,
    ErrorAccessDenied,
    ErrorFolderNotFound,
    ErrorInvalidFolderId,
    ErrorInvalidId,
    ErrorInvalidIdEmpty,
    ErrorInvalidIdMalformed,
    ErrorInvalidIdMalformedEwsLegacyIdFormat,
    ErrorInvalidIdMonikerTooLong,
    ErrorInvalidIdStoreObjectIdTooLong,
    ErrorInvalidNameForNameResolution,
    ErrorItemNotFound,
    ErrorParentFolderNotFound,
    ErrorServerBusy,
    ErrorTimeoutExpired,
    RateLimitError,
    ResponseMessageError,
    TransportError,
    UnauthorizedError,
)

NOT_FOUND_EXCEPTIONS = (
    DoesNotExist,
    ErrorItemNotFound,
    ErrorFolderNotFound,
    ErrorInvalidId,
    ErrorInvalidIdMalformed,
    ErrorInvalidIdEmpty,
    ErrorInvalidIdMalformedEwsLegacyIdFormat,
    ErrorInvalidIdMonikerTooLong,
    ErrorInvalidIdStoreObjectIdTooLong,
    ErrorInvalidFolderId,
    ErrorParentFolderNotFound,
)

WRITE_UNKNOWN_CODES = {"TIMEOUT_ERROR", "SERVER_BUSY", "CONNECTION_ERROR"}
WRITE_UNKNOWN_ADVICE = "Do not retry automatically. Reconcile with email list or calendar list."


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
        outcome: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.retryable = retryable
        self.details = details
        self.outcome = outcome

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": self.message,
            "code": self.code,
            "retryable": self.retryable,
        }
        if self.outcome:
            payload["outcome"] = self.outcome
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
    if isinstance(exc, ErrorAccessDenied):
        return CliError("Exchange denied access to the requested resource.", code="PERMISSION_ERROR")
    if isinstance(exc, (ErrorTimeoutExpired, TimeoutError)):
        return CliError("The Exchange operation timed out.", code="TIMEOUT_ERROR", retryable=True)
    if isinstance(exc, (ErrorServerBusy, RateLimitError)):
        return CliError("Exchange Server is busy. Retry later.", code="SERVER_BUSY", retryable=True)
    if isinstance(exc, NOT_FOUND_EXCEPTIONS):
        return CliError("The requested Exchange item or folder was not found.", code="NOT_FOUND")
    if isinstance(exc, ErrorInvalidNameForNameResolution):
        return CliError(str(exc) or "Invalid name for name resolution.", code="INVALID_INPUT", exit_code=2)
    if isinstance(exc, ResponseMessageError):
        return CliError(
            str(exc) or "Exchange Server returned an error.",
            code="SERVER_ERROR",
            retryable=False,
            details={"ews_error": type(exc).__name__},
        )
    if isinstance(exc, TransportError):
        return CliError("Could not connect to Exchange Server.", code="CONNECTION_ERROR", retryable=True)
    if isinstance(exc, (ValueError, TypeError)):
        return CliError(str(exc) or "Invalid input.", code="INVALID_INPUT", exit_code=2)
    return CliError(str(exc) or "Unexpected Exchange Server error.", code=default_code)


def classify_write_exception(exc: Exception, *, default_code: str = "SERVER_ERROR") -> CliError:
    """Classify a mutating Exchange call without inviting automatic retries."""

    error = classify_exception(exc, default_code=default_code)
    if error.code in WRITE_UNKNOWN_CODES:
        details = dict(error.details or {})
        details["advice"] = WRITE_UNKNOWN_ADVICE
        return CliError(
            "The write may have succeeded on the server, but the client did not receive a confirmed result.",
            code="WRITE_OUTCOME_UNKNOWN",
            exit_code=error.exit_code,
            retryable=False,
            details=details,
            outcome="unknown",
        )
    error.outcome = "failed"
    error.retryable = False
    return error
