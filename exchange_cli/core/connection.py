"""Connection management - lazy-load exchangelib Account objects."""

import os
import sys

import click
from exchangelib import BASIC, CBA, DELEGATE, DIGEST, GSSAPI, NTLM, OAUTH2, SSPI, Account, Configuration, Credentials
from exchangelib.errors import TransportError, UnauthorizedError
from exchangelib.protocol import BaseProtocol, NoVerifyHTTPAdapter
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from .config import ConfigManager

ERROR_CODES = {
    "CONFIG_NOT_FOUND": "No configuration found. Run: exchange-cli config init",
    "AUTH_ERROR": "Authentication failed. Check username/password.",
    "CONNECTION_ERROR": "Could not connect to Exchange server.",
    "INVALID_AUTH_TYPE": "Unsupported auth type.",
}

AUTH_TYPE_MAP = {
    "ntlm": NTLM,
    "basic": BASIC,
    "digest": DIGEST,
    "gssapi": GSSAPI,
    "sspi": SSPI,
    "oauth2": OAUTH2,
    "oauth 2.0": OAUTH2,
    "cba": CBA,
}

DEFAULT_HTTP_ADAPTER_CLS = BaseProtocol.HTTP_ADAPTER_CLS
TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}


def _resolve_auth_type(auth_type: str | None):
    if auth_type is None:
        return NTLM

    key = str(auth_type).strip().lower()
    resolved = AUTH_TYPE_MAP.get(key)
    if resolved is None:
        raise ValueError(f"{ERROR_CODES['INVALID_AUTH_TYPE']} {auth_type}")
    return resolved


def _parse_bool(value: str | bool | None) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in TRUTHY_VALUES:
        return True
    if normalized in FALSY_VALUES:
        return False
    return None


def _configure_http_adapter_from_env(no_verify_ssl: bool | None = None) -> None:
    env_value = _parse_bool(os.environ.get("EXCHANGE_NO_VERIFY_SSL"))
    resolved = env_value if env_value is not None else bool(no_verify_ssl)
    BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter if resolved else DEFAULT_HTTP_ADAPTER_CLS
    if resolved:
        disable_warnings(InsecureRequestWarning)


class ConnectionManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._accounts: dict[str, Account] = {}

    def get_account(self, email: str | None = None) -> Account:
        cache_key = email or "__default__"
        if cache_key in self._accounts:
            return self._accounts[cache_key]

        credentials_dict = self.config_manager.get_account_credentials(email)
        if not credentials_dict:
            click.echo(ERROR_CODES["CONFIG_NOT_FOUND"], err=True)
            sys.exit(1)
        _configure_http_adapter_from_env(no_verify_ssl=credentials_dict.get("no_verify_ssl"))

        try:
            credentials = Credentials(credentials_dict["username"], credentials_dict["password"])
            server = credentials_dict.get("server")
            auth_type = _resolve_auth_type(credentials_dict.get("auth_type"))
            primary_smtp_address = email or credentials_dict.get("email") or credentials_dict["username"]

            if server:
                config = Configuration(server=server, credentials=credentials, auth_type=auth_type)
                account = Account(
                    primary_smtp_address=primary_smtp_address,
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE,
                )
            else:
                account = Account(
                    primary_smtp_address=primary_smtp_address,
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE,
                )

            self._accounts[cache_key] = account
            return account
        except ValueError as exc:
            click.echo(str(exc), err=True)
            sys.exit(1)
        except UnauthorizedError:
            click.echo(ERROR_CODES["AUTH_ERROR"], err=True)
            sys.exit(1)
        except TransportError as exc:
            click.echo(f"{ERROR_CODES['CONNECTION_ERROR']}: {exc}", err=True)
            sys.exit(1)
