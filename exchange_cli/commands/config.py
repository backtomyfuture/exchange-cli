"""exchange-cli config {init, show, test}."""

import sys

import click
from exchangelib import DELEGATE, Account, Configuration, Credentials

from ..core.config import ConfigManager
from ..core.output import OutputFormatter


def _test_connection(server, username, password) -> bool:
    try:
        credentials = Credentials(username, password)
        config = Configuration(server=server, credentials=credentials)
        Account(
            primary_smtp_address=username,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
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

    server = click.prompt("Exchange Server", type=str)
    username = click.prompt("Username (e.g. DOMAIN\\user or user@domain.com)", type=str)
    password = click.prompt("Password", type=str, hide_input=True)
    auth_type = click.prompt("Auth type", type=click.Choice(["ntlm", "basic"]), default="ntlm")
    email = click.prompt("Email address", type=str)

    click.echo("Testing connection...", err=True)
    if _test_connection(server, username, password):
        click.echo("Connected successfully.", err=True)
    else:
        click.echo("Warning: Connection test failed. Saving config anyway.", err=True)

    config_manager.save_account(email, server, username, password, auth_type)
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
    if _test_connection(credentials["server"], credentials["username"], credentials["password"]):
        formatter.success({"message": "Connection successful", "server": credentials["server"]})
        return

    formatter.error("Connection failed", code="CONNECTION_ERROR")
    sys.exit(1)
