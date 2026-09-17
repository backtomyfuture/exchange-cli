import importlib
import logging
import sys
import time
import uuid

import click

from . import __version__
from .core.errors import CliError, classify_exception
from .core.output import OutputFormatter, set_current_request_context

# Suppress third-party warnings from exchangelib on stderr by default (e.g. paging offset warnings)
logging.getLogger("exchangelib").setLevel(logging.ERROR)

_CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

_COMMAND_MODULES = {
    "calendar": "exchange_cli.commands.calendar",
    "config": "exchange_cli.commands.config",
    "contact": "exchange_cli.commands.contact",
    "doctor": "exchange_cli.commands.doctor",
    "draft": "exchange_cli.commands.draft",
    "email": "exchange_cli.commands.email",
    "folder": "exchange_cli.commands.folder",
    "mailbox": "exchange_cli.commands.mailbox",
    "schema": "exchange_cli.commands.schema",
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


def _request_id_from_args(args) -> str:
    args = list(args or ())
    for index, arg in enumerate(args):
        if arg.startswith("--request-id="):
            val = arg.partition("=")[2].strip()
            if val:
                return val
        if arg == "--request-id" and index + 1 < len(args):
            val = args[index + 1].strip()
            if val:
                return val
    return str(uuid.uuid4())


GLOBAL_VALUE_OPTIONS = {"--format", "--config", "--account", "--request-id"}
GLOBAL_FLAG_OPTIONS = {"--verbose", "-v"}
KNOWN_PARAMETRIZED_OPTIONS = {
    "--to",
    "--from",
    "--cc",
    "--bcc",
    "--subject",
    "--body",
    "--body-file",
    "--body-type",
    "--body-format",
    "--attach",
    "--inline-attach",
    "--reply-to",
    "--category",
    "--importance",
    "--sensitivity",
    "--fields",
    "--save-attachments",
    "--folder",
    "--limit",
    "--offset",
    "--start",
    "--end",
    "--location",
    "--attendees",
    "--notify",
    "--due",
    "--status",
    "--ca-bundle",
    "--preset",
    "--max-body-length",
    "--if-changekey",
    "--conflict-resolution",
    "--sent-folder",
    "--input",
    "--output",
    "--response",
    "--propose-start",
    "--propose-end",
    "--state",
    "--external-audience",
    "--internal-reply",
    "--internal-reply-file",
    "--external-reply",
    "--external-reply-file",
    "--parent",
    "--name",
    "--request",
    "--spec-file",
    "--attachment-id",
}


def _hoist_global_args(args: list[str]) -> list[str]:
    """Allow human users to specify top-level global options anywhere in the command line.

    For example, moves trailing '--format text' or '--account foo' before the subcommand:
        ['email', 'list', '--format', 'text'] -> ['--format', 'text', 'email', 'list']
    """
    args = list(args)
    hoisted: list[str] = []
    remaining: list[str] = []

    index = 0
    while index < len(args):
        arg = args[index]

        # Explicit option with value via '=': e.g. --format=text
        matched_prefix = next((opt for opt in GLOBAL_VALUE_OPTIONS if arg.startswith(f"{opt}=")), None)
        if matched_prefix:
            hoisted.append(arg)
            index += 1
            continue

        # Option with value in the next token: e.g. --format text
        if arg in GLOBAL_VALUE_OPTIONS:
            hoisted.append(arg)
            if index + 1 < len(args):
                hoisted.append(args[index + 1])
                index += 2
            else:
                index += 1
            continue

        # Global flag option: e.g. --verbose or -v
        if arg in GLOBAL_FLAG_OPTIONS:
            hoisted.append(arg)
            index += 1
            continue

        # If this is a known subcommand option that consumes a parameter, preserve both
        if arg in KNOWN_PARAMETRIZED_OPTIONS:
            remaining.append(arg)
            if index + 1 < len(args):
                remaining.append(args[index + 1])
                index += 2
            else:
                index += 1
            continue

        remaining.append(arg)
        index += 1

    return hoisted + remaining


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
        normalized_args = _hoist_global_args(raw_args)
        req_id = _request_id_from_args(raw_args)
        start_t = time.monotonic()
        set_current_request_context(req_id, start_t)
        try:
            try:
                return super().main(
                    args=normalized_args,
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

            formatter = OutputFormatter(_format_from_args(raw_args), request_id=req_id, start_time=start_t)
            formatter.error(
                cli_error.message,
                code=cli_error.code,
                retryable=cli_error.retryable,
                details=cli_error.details,
                outcome=cli_error.outcome,
            )
            if standalone_mode:
                raise SystemExit(cli_error.exit_code)
            return cli_error.exit_code
        finally:
            set_current_request_context(None, None)


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
@click.option(
    "--request-id",
    "request_id",
    default=None,
    help="Client-assigned tracking UUID for Exchange requests",
)
@click.option("--verbose", is_flag=True, default=False, help="Verbose output to stderr")
@click.pass_context
def cli(ctx, fmt, config_path, account_email, request_id, verbose):
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
    ctx.obj["request_id"] = request_id or _request_id_from_args([])
    ctx.obj["start_time"] = time.monotonic()
    if verbose:
        logging.getLogger("exchangelib").setLevel(logging.DEBUG)


def main():
    cli()


if __name__ == "__main__":
    main()
