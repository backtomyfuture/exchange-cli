import json

from exchange_cli import __version__
from exchange_cli.main import cli


def test_click_validation_uses_json_contract(runner):
    result = runner.invoke(cli, ["email", "send"])

    assert result.exit_code == 2
    assert result.stderr == ""
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["error"] == "Missing option '--to'."
    assert data["code"] == "INVALID_INPUT"
    assert data["retryable"] is False
    assert "request_id" in data and data["request_id"]


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
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["error"] == "No configuration found. Run: exchange-cli config init"
    assert data["code"] == "CONFIG_NOT_FOUND"
    assert data["retryable"] is False
    assert "request_id" in data and data["request_id"]


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
    assert payload["data"]["schema_version"] == 2


def test_schema_single_command(runner):
    result = runner.invoke(cli, ["schema", "email.send"])

    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    assert payload["name"] == "email.send"
    assert payload["write"] is True
    assert payload["confirm"] is True
    assert payload["effect"] == "external_send"
    assert payload["confirmation"] == "required"
    assert payload["retry"] == "never_on_unknown_outcome"
    option_names = {opt["name"] for opt in payload["options"]}
    assert "--to" in option_names
    assert "--confirm" in option_names


def test_schema_calendar_command_semantics(runner):
    result = runner.invoke(cli, ["schema", "calendar.create"])
    assert result.exit_code == 0
    create_data = json.loads(result.output)["data"]
    assert create_data["confirm"] is True
    assert create_data["effect"] == "conditional"
    assert create_data["confirmation"] == "conditional"

    result = runner.invoke(cli, ["schema", "calendar.update"])
    assert result.exit_code == 0
    update_data = json.loads(result.output)["data"]
    assert update_data["confirm"] is False
    assert update_data["effect"] == "conditional"
    assert update_data["confirmation"] == "conditional"

    result = runner.invoke(cli, ["schema", "calendar.delete"])
    assert result.exit_code == 0
    delete_data = json.loads(result.output)["data"]
    assert delete_data["confirm"] is True
    assert delete_data["effect"] == "internal_modify"
    assert delete_data["confirmation"] == "required"


def test_schema_command_with_arguments(runner):
    result = runner.invoke(cli, ["schema", "email.read"])

    assert result.exit_code == 0
    payload = json.loads(result.output)["data"]
    assert payload["name"] == "email.read"
    assert payload["write"] is False
    assert any(arg["name"] == "message_id" for arg in payload["arguments"])
    option_names = {opt["name"] for opt in payload["options"]}
    assert "--include-html" in option_names
    assert "--max-body-length" in option_names


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


def test_explicit_request_id_in_error(runner):
    result = runner.invoke(cli, ["--request-id", "custom-req-123", "email", "send"])
    assert result.exit_code == 2
    data = json.loads(result.stdout)
    assert data["request_id"] == "custom-req-123"


def test_explicit_request_id_in_schema_success(runner):
    result = runner.invoke(cli, ["--request-id", "req-schema-456", "schema", "email.send"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["meta"]["request_id"] == "req-schema-456"
    assert "elapsed_ms" in data["meta"]

