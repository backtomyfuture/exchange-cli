import json

from exchange_cli import __version__
from exchange_cli.main import cli


def test_click_validation_uses_json_contract(runner):
    result = runner.invoke(cli, ["email", "send"])

    assert result.exit_code == 2
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "Missing option '--to'.",
        "code": "INVALID_INPUT",
        "retryable": False,
    }


def test_click_validation_respects_text_format(runner):
    result = runner.invoke(cli, ["--format", "text", "email", "send"])

    assert result.exit_code == 2
    assert result.stderr == ""
    assert result.stdout == "Error [INVALID_INPUT]: Missing option '--to'.\n"


def test_missing_config_uses_json_contract(runner, tmp_path):
    clean_env = {
        "EXCHANGE_SERVER": None,
        "EXCHANGE_USERNAME": None,
        "EXCHANGE_PASSWORD": None,
        "EXCHANGE_DOMAIN": None,
        "EXCHANGE_EMAIL": None,
    }
    result = runner.invoke(cli, ["--config", str(tmp_path), "email", "list"], env=clean_env)

    assert result.exit_code == 1
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "No configuration found. Run: exchange-cli config init",
        "code": "CONFIG_NOT_FOUND",
        "retryable": False,
    }


def test_help_remains_human_readable_success(runner):
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output


def test_version_remains_human_readable_success(runner):
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert result.output == f"exchange-cli, version {__version__}\n"


def test_unknown_command_uses_json_contract(runner):
    result = runner.invoke(cli, ["unknown"])

    assert result.exit_code == 2
    assert json.loads(result.output)["code"] == "INVALID_INPUT"


def test_help_exposes_no_daemon_command(runner):
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "\n  daemon" not in result.output
    assert "\n  schema" in result.output


def test_schema_lists_commands(runner):
    result = runner.invoke(cli, ["schema"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    names = {item["name"] for item in payload["data"]["commands"]}
    assert "email.send" in names
    assert "contact.resolve" in names
    assert payload["data"]["schema_version"] == 1


def test_schema_single_command(runner):
    result = runner.invoke(cli, ["schema", "email.send"])

    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    assert payload["name"] == "email.send"
    assert payload["write"] is True
    assert payload["confirm"] is True


def test_trailing_format_option_is_hoisted(runner):
    result = runner.invoke(cli, ["email", "send", "--format", "text"])

    assert result.exit_code == 2
    assert result.stdout == "Error [INVALID_INPUT]: Missing option '--to'.\n"


def test_trailing_config_option_is_hoisted(runner, tmp_path):
    clean_env = {
        "EXCHANGE_SERVER": None,
        "EXCHANGE_USERNAME": None,
        "EXCHANGE_PASSWORD": None,
        "EXCHANGE_DOMAIN": None,
        "EXCHANGE_EMAIL": None,
    }
    result = runner.invoke(cli, ["email", "list", "--config", str(tmp_path)], env=clean_env)

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["code"] == "CONFIG_NOT_FOUND"


def test_trailing_format_equal_syntax_is_hoisted(runner):
    result = runner.invoke(cli, ["email", "send", "--format=text"])

    assert result.exit_code == 2
    assert result.stdout == "Error [INVALID_INPUT]: Missing option '--to'.\n"
