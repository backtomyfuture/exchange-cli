import click
import pytest
from exchangelib.errors import (
    DoesNotExist,
    ErrorAccessDenied,
    ErrorFolderNotFound,
    ErrorInvalidIdMalformed,
    ErrorServerBusy,
    ErrorTimeoutExpired,
    ResponseMessageError,
    TransportError,
    UnauthorizedError,
)

from exchange_cli.core.errors import CliError, classify_exception, classify_write_exception


@pytest.mark.parametrize(
    ("exception", "code", "exit_code", "retryable"),
    [
        (DoesNotExist("missing"), "NOT_FOUND", 1, False),
        (ErrorFolderNotFound("missing folder"), "NOT_FOUND", 1, False),
        (ErrorInvalidIdMalformed("bad id format"), "NOT_FOUND", 1, False),
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


@pytest.mark.parametrize(
    "exception",
    [
        ErrorTimeoutExpired("timeout"),
        TimeoutError("timeout"),
        ErrorServerBusy("busy"),
        TransportError("offline"),
    ],
)
def test_write_timeout_and_transport_errors_are_unknown_and_not_retryable(exception):
    error = classify_write_exception(exception)

    assert error.code == "WRITE_OUTCOME_UNKNOWN"
    assert error.retryable is False
    assert error.outcome == "unknown"
    assert error.details["advice"] == "Do not retry automatically. Reconcile with email list or calendar list."


def test_write_auth_error_stays_failed_and_not_retryable():
    error = classify_write_exception(UnauthorizedError("bad credentials"))

    assert error.code == "AUTH_ERROR"
    assert error.retryable is False
    assert error.outcome == "failed"


def test_write_unknown_error_serializes_outcome():
    error = classify_write_exception(TimeoutError("timeout"))

    assert error.to_dict()["outcome"] == "unknown"
    assert error.to_dict()["retryable"] is False


def test_classify_response_message_error_as_server_error():
    exc = ResponseMessageError("something failed on server")
    error = classify_exception(exc)

    assert error.code == "SERVER_ERROR"
    assert error.retryable is False
    assert error.details == {"ews_error": "ResponseMessageError"}


def test_write_invalid_id_is_not_found_and_not_unknown():
    error = classify_write_exception(ErrorInvalidIdMalformed("invalid id format"))

    assert error.code == "NOT_FOUND"
    assert error.retryable is False
    assert error.outcome == "failed"


def test_classify_invalid_name_resolution_as_invalid_input():
    from exchangelib.errors import ErrorInvalidNameForNameResolution

    error = classify_exception(ErrorInvalidNameForNameResolution("invalid name"))
    assert error.code == "INVALID_INPUT"
    assert error.exit_code == 2
    assert error.retryable is False


def test_classify_write_exception_omits_outcome_for_non_mutating_codes():
    error_confirm = classify_write_exception(CliError("Confirmation needed", code="CONFIRMATION_REQUIRED", exit_code=2))
    assert error_confirm.code == "CONFIRMATION_REQUIRED"
    assert error_confirm.outcome is None

    error_input = classify_write_exception(ValueError("Bad value"))
    assert error_input.code == "INVALID_INPUT"
    assert error_input.outcome is None

