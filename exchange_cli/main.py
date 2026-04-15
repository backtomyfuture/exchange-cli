import importlib

import click

from . import __version__

_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

_COMMAND_MODULES = {
    "calendar": "exchange_cli.commands.calendar",
    "config": "exchange_cli.commands.config",
    "contact": "exchange_cli.commands.contact",
    "daemon": "exchange_cli.commands.daemon",
    "draft": "exchange_cli.commands.draft",
    "email": "exchange_cli.commands.email",
    "folder": "exchange_cli.commands.folder",
    "task": "exchange_cli.commands.task",
}


class LazyGroup(click.Group):
    """Click Group that defers command module imports until the command is invoked."""

    def get_command(self, ctx, cmd_name):
        if cmd_name in _COMMAND_MODULES:
            mod = importlib.import_module(_COMMAND_MODULES[cmd_name])
            return getattr(mod, cmd_name)
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx):
        return sorted(_COMMAND_MODULES.keys())


@click.group(cls=LazyGroup, context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=__version__, prog_name="exchange-cli")
@click.option(
    "--format",
    "fmt",
    default="json",
    type=click.Choice(["json", "text"]),
    help="Output format (default: json)",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="EXCHANGE_CLI_CONFIG",
    help="Config file path",
)
@click.option("--account", "account_email", default=None, help="Account email (overrides default)")
@click.option("--verbose", is_flag=True, default=False, help="Verbose output to stderr")
@click.pass_context
def cli(ctx, fmt, config_path, account_email, verbose):
    """exchange-cli - Exchange Web Services CLI for AI agents.

    \b
    Quick start:
      exchange-cli config init
      exchange-cli email list
      exchange-cli email read MSG_ID
      exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
    """
    ctx.ensure_object(dict)
    ctx.obj["fmt"] = fmt
    ctx.obj["config_path"] = config_path
    ctx.obj["account_email"] = account_email
    ctx.obj["verbose"] = verbose


def main():
    cli()


if __name__ == "__main__":
    main()
