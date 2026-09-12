"""exchange-cli config {init, show}."""

import os

import click

from ..core.config import DEFAULT_TIMEOUT_SECONDS, ConfigManager
from ..core.connection import probe_connection
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


@click.group("config")
@click.pass_context
def config(ctx):
    """Manage exchange-cli configuration."""


@config.command("init")
@click.option("--ca-bundle", type=click.Path(dir_okay=False), default=None, help="Path to enterprise CA bundle.")
@click.pass_context
def config_init(ctx, ca_bundle):
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
    parts = server.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        click.echo(
            "Notice: Using an IP address instead of a domain name often causes TLS certificate verification to fail.",
            err=True,
        )

    username = _normalize_text(username) or username
    auth_type = _normalize_text(auth_type, lower=True) or auth_type
    email = _normalize_text(email) or email

    ca_bundle_resolved = ca_bundle or os.environ.get("EXCHANGE_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca_bundle_resolved:
        ca_bundle_resolved = ca_bundle_resolved.strip() or None

    no_verify_default = os.environ.get("EXCHANGE_NO_VERIFY_SSL", "").strip().lower() in TRUTHY_VALUES
    no_verify_ssl = click.confirm("Disable SSL certificate verification", default=no_verify_default)
    if no_verify_ssl:
        click.echo(
            "Warning: Disabling SSL certificate verification is insecure and will cause 'exchange-cli doctor' to fail.",
            err=True,
        )

    click.echo("Testing connection...", err=True)
    try:
        timeout_seconds = config_manager.parse_timeout(
            os.environ.get("EXCHANGE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        probe_payload = {
            "email": email,
            "server": server,
            "username": username,
            "password": password,
            "auth_type": auth_type,
            "no_verify_ssl": no_verify_ssl,
            "timeout_seconds": timeout_seconds,
        }
        if ca_bundle_resolved:
            probe_payload["ca_bundle"] = ca_bundle_resolved

        if not probe_connection(probe_payload):
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

    config_manager.save_account(
        email,
        server,
        username,
        password,
        auth_type,
        no_verify_ssl=no_verify_ssl,
        ca_bundle=ca_bundle_resolved,
    )
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
