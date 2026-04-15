"""Connection management - lazy-load exchangelib Account objects."""

import sys

import click
from exchangelib import Account, Configuration, Credentials, DELEGATE
from exchangelib.errors import TransportError, UnauthorizedError

from .config import ConfigManager

ERROR_CODES = {
    "CONFIG_NOT_FOUND": "No configuration found. Run: exchange-cli config init",
    "AUTH_ERROR": "Authentication failed. Check username/password.",
    "CONNECTION_ERROR": "Could not connect to Exchange server.",
}


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

        try:
            credentials = Credentials(credentials_dict["username"], credentials_dict["password"])
            server = credentials_dict.get("server")
            primary_smtp_address = email or credentials_dict["username"]

            if server:
                config = Configuration(server=server, credentials=credentials)
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
        except UnauthorizedError:
            click.echo(ERROR_CODES["AUTH_ERROR"], err=True)
            sys.exit(1)
        except TransportError as exc:
            click.echo(f"{ERROR_CODES['CONNECTION_ERROR']}: {exc}", err=True)
            sys.exit(1)
