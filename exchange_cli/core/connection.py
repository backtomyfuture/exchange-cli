"""Single-account Exchange connection management."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from exchangelib import BASIC, DELEGATE, NTLM, Account, Configuration, Credentials
from exchangelib.errors import TransportError, UnauthorizedError
from exchangelib.protocol import BaseProtocol, FailFast, NoVerifyHTTPAdapter
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from .config import ConfigManager
from .errors import CliError

ERROR_CODES = {
    "CONFIG_NOT_FOUND": "No configuration found. Run: exchange-cli config init",
    "AUTH_ERROR": "Authentication failed. Check username/password.",
    "CONNECTION_ERROR": "Could not connect to Exchange server.",
    "INVALID_AUTH_TYPE": "Unsupported auth type.",
}

AUTH_TYPE_MAP = {
    "ntlm": NTLM,
    "basic": BASIC,
}

DEFAULT_HTTP_ADAPTER_CLS = BaseProtocol.HTTP_ADAPTER_CLS


def _resolve_auth_type(auth_type: str | None):
    key = "ntlm" if auth_type is None else str(auth_type).strip().lower()
    resolved = AUTH_TYPE_MAP.get(key)
    if resolved is None:
        raise CliError(
            f"{ERROR_CODES['INVALID_AUTH_TYPE']} {auth_type}",
            code="INVALID_AUTH_TYPE",
            exit_code=2,
        )
    return resolved


def _configure_http_adapter(no_verify_ssl: bool) -> None:
    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter if no_verify_ssl else DEFAULT_HTTP_ADAPTER_CLS
    if no_verify_ssl:
        disable_warnings(InsecureRequestWarning)


def create_account(credentials_dict: dict[str, Any]) -> Account:
    """Create an Account with bounded, fail-fast on-premises settings."""

    _configure_http_adapter(bool(credentials_dict.get("no_verify_ssl", False)))
    BaseProtocol.TIMEOUT = int(credentials_dict["timeout_seconds"])
    auth_type = _resolve_auth_type(credentials_dict.get("auth_type"))
    try:
        credentials = Credentials(credentials_dict["username"], credentials_dict["password"])
        config = Configuration(
            server=credentials_dict["server"],
            credentials=credentials,
            auth_type=auth_type,
            retry_policy=FailFast(),
            max_connections=1,
        )
        return Account(
            primary_smtp_address=credentials_dict["email"],
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
    except CliError:
        raise
    except ValueError as exc:
        raise CliError(
            "Exchange credentials or account identity are invalid.",
            code="CONFIG_INVALID",
            exit_code=2,
        ) from exc
    except UnauthorizedError as exc:
        raise CliError(ERROR_CODES["AUTH_ERROR"], code="AUTH_ERROR") from exc
    except TransportError as exc:
        raise CliError(
            ERROR_CODES["CONNECTION_ERROR"],
            code="CONNECTION_ERROR",
            retryable=True,
        ) from exc


def probe_connection(credentials_dict: dict[str, Any]) -> bool:
    """Authenticate and perform the smallest read-only EWS operation."""

    required_fields = ("email", "server", "username", "password")
    if any(
        not isinstance(credentials_dict.get(field), str) or not credentials_dict[field].strip()
        for field in required_fields
    ):
        return False

    account = create_account(credentials_dict)
    account.root.refresh()
    return True


def _credentials_fingerprint(credentials_dict: dict[str, Any]) -> str:
    serialized = json.dumps(credentials_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def _close_account(account: Account | None) -> None:
    if account is None:
        return
    protocol = getattr(account, "protocol", None)
    close = getattr(protocol, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


class ConnectionManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._account: Account | None = None
        self._fingerprint: str | None = None

    def get_account(self, email: str | None = None) -> Account:
        credentials_dict = self.config_manager.get_account_credentials(email)
        if not credentials_dict:
            raise CliError(ERROR_CODES["CONFIG_NOT_FOUND"], code="CONFIG_NOT_FOUND")

        fingerprint = _credentials_fingerprint(credentials_dict)
        if self._account is not None and fingerprint == self._fingerprint:
            return self._account

        account = create_account(credentials_dict)
        old_account = self._account
        self._account = account
        self._fingerprint = fingerprint
        if old_account is not account:
            _close_account(old_account)
        return account

    def close(self) -> None:
        _close_account(self._account)
        self._account = None
        self._fingerprint = None
