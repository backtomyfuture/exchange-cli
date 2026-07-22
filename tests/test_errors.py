import click
import pytest
from exchangelib.errors import (
    DoesNotExist,
    ErrorAccessDenied,
    ErrorServerBusy,
    ErrorTimeoutExpired,
    TransportError,
    UnauthorizedError,
)

from exchange_cli.core.errors import CliError, classify_exception


@pytest.mark.parametrize(
    ("exception", "code", "exit_code", "retryable"),
    [
        (DoesNotExist("missing"), "NOT_FOUND", 1, False),
        (ErrorAccessDenied("denied"), "PERMISSION_ERROR", 1, False),
        (ErrorTimeoutExpired("timeout"), "TIMEOUT_ERROR", 1, True),
        (TimeoutError("timeout"), "TIMEOUT_ERROR", 1, True),
        (ErrorServerBusy("busy"), "SERVER_BUSY", 1, True),
        (TransportError("offline"), "CONNECTION_ERROR", 1, True),
        (UnauthorizedError("bad credentials"), "AUTH_ERROR", 1, False),
        (ValueError("bad value"), "INVALID_INPUT", 2, False),
    ],
)
def test_classify_exception(exception, code, exit_code, retryable):
    error = classify_exception(exception)

    assert error.code == code
    assert error.exit_code == exit_code
    assert error.retryable is retryable


def test_classify_preserves_cli_error():
    original = CliError("known", code="KNOWN", details={"field": "folder"})

    assert classify_exception(original) is original


def test_classify_click_exception_as_invalid_input():
    error = classify_exception(click.UsageError("bad usage"))

    assert error.code == "INVALID_INPUT"
    assert error.exit_code == 2
