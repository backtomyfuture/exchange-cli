"""exchange-cli config {init, show, test}."""

import os
import sys

import click
from exchangelib import DELEGATE, Account, Configuration, Credentials

from ..core.config import ConfigManager
from ..core.connection import _configure_http_adapter_from_env, _resolve_auth_type
from ..core.output import OutputFormatter

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _derive_email_from_username(username: str | None, suffix: str | None) -> str | None:
    if not username or not suffix:
        return None
    normalized_suffix = suffix if suffix.startswith("@") else f"@{suffix}"
    local_part = username.split("\\")[-1]
    if "@" in local_part:
        local_part = local_part.split("@", 1)[0]
    local_part = local_part.strip()
    if not local_part:
        return None
    return f"{local_part}{normalized_suffix}"


def _test_connection(
    server,
    username,
    password,
    auth_type="ntlm",
    primary_smtp_address=None,
    no_verify_ssl=False,
) -> bool:
    try:
        _configure_http_adapter_from_env(no_verify_ssl=no_verify_ssl)
        credentials = Credentials(username, password)
        config = Configuration(server=server, credentials=credentials, auth_type=_resolve_auth_type(auth_type))
        account = Account(
            primary_smtp_address=primary_smtp_address or username,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
        account.root.refresh()
        return True
    except Exception:
        return False


@click.group("config")
@click.pass_context
def config(ctx):
    """Manage exchange-cli configuration."""


@config.command("init")
@click.pass_context
def config_init(ctx):
    """Interactive setup for Exchange server credentials."""
    config_path = ctx.obj.get("config_path")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()

    existing = config_manager.load_config()
    if existing:
        click.echo("Existing configuration found.", err=True)
        if not click.confirm("Add a new account or overwrite?", default=True):
            sys.exit(0)

    server_default = os.environ.get("EXCHANGE_SERVER")
    if server_default:
        server = click.prompt("Exchange Server", type=str, default=server_default, show_default=True)
    else:
        server = click.prompt("Exchange Server", type=str)

    username_default = os.environ.get("EXCHANGE_USERNAME")
    if not username_default:
        env_domain = os.environ.get("EXCHANGE_DOMAIN")
        current_user = os.environ.get("USER")
        if env_domain and current_user:
            username_default = f"{env_domain}\\{current_user}"

    if username_default:
        username = click.prompt(
            "Username (e.g. DOMAIN\\user or user@domain.com)",
            type=str,
            default=username_default,
            show_default=True,
        )
    else:
        username = click.prompt("Username (e.g. DOMAIN\\user or user@domain.com)", type=str)

    password = click.prompt("Password", type=str, hide_input=True)
    auth_default = os.environ.get("EXCHANGE_AUTH_TYPE", "ntlm").lower()
    if auth_default not in {"ntlm", "basic"}:
        auth_default = "ntlm"
    auth_type = click.prompt("Auth type", type=click.Choice(["ntlm", "basic"]), default=auth_default)

    email_default = os.environ.get("EXCHANGE_EMAIL")
    if not email_default:
        email_default = _derive_email_from_username(username, os.environ.get("EXCHANGE_EMAIL_SUFFIX"))
    if email_default:
        email = click.prompt("Email address", type=str, default=email_default, show_default=True)
    else:
        email = click.prompt("Email address", type=str)

    no_verify_default = os.environ.get("EXCHANGE_NO_VERIFY_SSL", "").strip().lower() in TRUTHY_VALUES
    no_verify_ssl = click.confirm("Disable SSL certificate verification", default=no_verify_default)

    click.echo("Testing connection...", err=True)
    if _test_connection(server, username, password, auth_type, email, no_verify_ssl):
        click.echo("Connected successfully.", err=True)
    else:
        click.echo("Warning: Connection test failed. Saving config anyway.", err=True)

    config_manager.save_account(email, server, username, password, auth_type, no_verify_ssl=no_verify_ssl)
    click.echo(f"Configuration saved to {config_manager.config_path}", err=True)

    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    formatter.success({"message": "Configuration saved", "account": email})


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration with masked passwords."""
    config_path = ctx.obj.get("config_path")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    display = config_manager.get_display_config()
    if not display:
        formatter.error("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
        sys.exit(1)
    formatter.success(display)


@config.command("test")
@click.pass_context
def config_test(ctx):
    """Test connection to Exchange server."""
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    credentials = config_manager.get_account_credentials(account_email)
    if not credentials:
        formatter.error("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
        sys.exit(1)

    click.echo("Testing connection...", err=True)
    if _test_connection(
        credentials["server"],
        credentials["username"],
        credentials["password"],
        credentials.get("auth_type", "ntlm"),
        account_email or credentials.get("email"),
        credentials.get("no_verify_ssl", False),
    ):
        formatter.success({"message": "Connection successful", "server": credentials["server"]})
        return

    formatter.error("Connection failed", code="CONNECTION_ERROR")
    sys.exit(1)
