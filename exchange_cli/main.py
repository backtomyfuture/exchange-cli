import importlib
import sys

import click

from . import __version__
from .core.errors import CliError, classify_exception
from .core.output import OutputFormatter

_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

_COMMAND_MODULES = {
    "calendar": "exchange_cli.commands.calendar",
    "config": "exchange_cli.commands.config",
    "contact": "exchange_cli.commands.contact",
    "doctor": "exchange_cli.commands.doctor",
    "draft": "exchange_cli.commands.draft",
    "email": "exchange_cli.commands.email",
    "folder": "exchange_cli.commands.folder",
    "task": "exchange_cli.commands.task",
}


def _format_from_args(args) -> str:
    args = list(args or ())
    for index, arg in enumerate(args):
        if arg.startswith("--format="):
            value = arg.partition("=")[2]
            return value if value in {"json", "text"} else "json"
        if arg == "--format" and index + 1 < len(args):
            value = args[index + 1]
            return value if value in {"json", "text"} else "json"
    return "json"


class LazyGroup(click.Group):
    """Click Group that defers command module imports until the command is invoked."""

    def get_command(self, ctx, cmd_name):
        if cmd_name in _COMMAND_MODULES:
            mod = importlib.import_module(_COMMAND_MODULES[cmd_name])
            return getattr(mod, cmd_name)
        return super().get_command(ctx, cmd_name)

    def list_commands(self, ctx):
        return sorted(_COMMAND_MODULES.keys())

    def main(
        self,
        args=None,
        prog_name=None,
        complete_var=None,
        standalone_mode=True,
        windows_expand_args=True,
        **extra,
    ):
        """Run Click without its human-only exception renderer."""

        raw_args = list(sys.argv[1:] if args is None else args)
        try:
            return super().main(
                args=raw_args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except click.ClickException as exc:
            cli_error = CliError(exc.format_message(), code="INVALID_INPUT", exit_code=exc.exit_code)
        except click.Abort:
            cli_error = CliError("Operation aborted.", code="ABORTED", exit_code=1)
        except Exception as exc:
            cli_error = classify_exception(exc)

        formatter = OutputFormatter(_format_from_args(raw_args))
        formatter.error(
            cli_error.message,
            code=cli_error.code,
            retryable=cli_error.retryable,
            details=cli_error.details,
        )
        if standalone_mode:
            raise SystemExit(cli_error.exit_code)
        return cli_error.exit_code


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
    help="Configuration directory path",
)
@click.option(
    "--account",
    "account_email",
    default=None,
    help="Compatibility assertion; must match the configured single account",
)
@click.option("--verbose", is_flag=True, default=False, help="Verbose output to stderr")
@click.pass_context
def cli(ctx, fmt, config_path, account_email, verbose):
    """exchange-cli - Exchange Web Services CLI for AI agents.

    \b
    Quick start:
      exchange-cli config init
      exchange-cli doctor
      exchange-cli email list
      exchange-cli email read MSG_ID
      exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello" --confirm
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
