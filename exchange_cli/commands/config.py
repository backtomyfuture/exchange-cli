"""exchange-cli config {init, show, test}."""

import os

import click

from ..core.config import DEFAULT_TIMEOUT_SECONDS, ConfigManager
from ..core.connection import create_account
from ..core.errors import CliError, classify_exception
from ..core.output import OutputFormatter

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _normalize_text(value: str | None, *, lower: bool = False) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.lower() if lower else normalized


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
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    normalized_server = _normalize_text(server)
    normalized_username = _normalize_text(username)
    normalized_auth_type = _normalize_text(auth_type, lower=True) or "ntlm"
    normalized_primary_smtp_address = _normalize_text(primary_smtp_address)
    if not normalized_server or not normalized_username or not normalized_primary_smtp_address:
        return False
    account = create_account(
        {
            "email": normalized_primary_smtp_address,
            "server": normalized_server,
            "username": normalized_username,
            "password": password,
            "auth_type": normalized_auth_type,
            "no_verify_ssl": bool(no_verify_ssl),
            "timeout_seconds": timeout_seconds,
        }
    )
    account.root.refresh()
    return True


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
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    if config_manager.config_path.exists() or config_manager.config_path.is_symlink():
        click.echo("Existing configuration found.", err=True)
        if not click.confirm("Overwrite the existing single-account configuration?", default=False):
            formatter.success({"message": "Configuration unchanged", "changed": False})
            return

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

    server = _normalize_text(server) or server
    username = _normalize_text(username) or username
    auth_type = _normalize_text(auth_type, lower=True) or auth_type
    email = _normalize_text(email) or email

    no_verify_default = os.environ.get("EXCHANGE_NO_VERIFY_SSL", "").strip().lower() in TRUTHY_VALUES
    no_verify_ssl = click.confirm("Disable SSL certificate verification", default=no_verify_default)

    click.echo("Testing connection...", err=True)
    try:
        timeout_seconds = config_manager.parse_timeout(
            os.environ.get("EXCHANGE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        if not _test_connection(
            server,
            username,
            password,
            auth_type,
            email,
            no_verify_ssl,
            timeout_seconds,
        ):
            raise CliError("Connection failed.", code="CONNECTION_ERROR", retryable=True)
        click.echo("Connected successfully.", err=True)
    except Exception as exc:
        test_error = classify_exception(exc)
        click.echo(f"Connection test failed [{test_error.code}]: {test_error.message}", err=True)
        if not click.confirm("Save this unverified configuration anyway?", default=False):
            formatter.success(
                {
                    "message": "Configuration not saved",
                    "changed": False,
                    "test_error": test_error.code,
                }
            )
            return

    config_manager.save_account(email, server, username, password, auth_type, no_verify_ssl=no_verify_ssl)
    click.echo(f"Configuration saved to {config_manager.config_path}", err=True)

    formatter.success({"message": "Configuration saved", "account": email, "changed": True})


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration with masked passwords."""
    config_path = ctx.obj.get("config_path")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    display = config_manager.get_display_config()
    if not display:
        raise CliError("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
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
        raise CliError("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")

    click.echo("Testing connection...", err=True)
    try:
        connected = _test_connection(
            credentials["server"],
            credentials["username"],
            credentials["password"],
            credentials.get("auth_type", "ntlm"),
            credentials["email"],
            credentials.get("no_verify_ssl", False),
            credentials["timeout_seconds"],
        )
        if not connected:
            raise CliError("Connection failed.", code="CONNECTION_ERROR", retryable=True)
    except Exception as exc:
        raise classify_exception(exc) from exc
    formatter.success({"message": "Connection successful", "server": credentials["server"]})
