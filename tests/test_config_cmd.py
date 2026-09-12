import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from exchange_cli.core.errors import CliError
from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


class TestConfigInit:
    def test_init_interactive(self, runner, tmp_path):
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        assert "saved" in result.output.lower() or "ok" in result.output.lower()
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["no_verify_ssl"] is False
        assert saved["accounts"]["test@example.com"]["auth_type"] == "ntlm"

    def test_init_overwrites_instead_of_adding(self, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        config_dir = tmp_path / ".exchange-cli"
        manager = ConfigManager(config_dir=config_dir)
        manager.save_account("old@example.com", "old.example.com", "old", "oldpass", "ntlm")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="y\nmail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )

        assert result.exit_code == 0
        assert list(manager.load_config()["accounts"]) == ["test@example.com"]

    def test_failed_probe_does_not_save_without_confirmation(self, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        with patch(
            "exchange_cli.commands.config.probe_connection",
            side_effect=CliError("Authentication failed", code="AUTH_ERROR"),
        ):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\nn\n",
            )

        assert result.exit_code == 0
        assert not (config_dir / "config.json").exists()
        assert '"changed": false' in result.stdout.lower()

    def test_init_can_recover_corrupt_config(self, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("{broken", encoding="utf-8")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="y\nmail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )

        assert result.exit_code == 0
        assert json.loads((config_dir / "config.json").read_text(encoding="utf-8"))["version"] == 1

    def test_init_with_preset_company(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("USER", "testuser")
        config_dir = tmp_path / ".exchange-cli"
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init", "--preset", "company"],
                input="\n\nsecret123\n\n",
            )

        assert result.exit_code == 0
        saved = json.loads((config_dir / "config.json").read_text(encoding="utf-8"))
        assert saved["default_account"] == "testuser@tianjin-air.com"
        account = saved["accounts"]["testuser@tianjin-air.com"]
        assert account["server"] == "mail.hnair.net"
        assert account["username"] == "hnanet\\testuser"
        assert account["auth_type"] == "ntlm"
        assert account["no_verify_ssl"] is False

    def test_init_with_insecure_flag(self, runner, tmp_path):
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init", "--insecure"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        assert "warning: disabling ssl" in result.output.lower()
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["no_verify_ssl"] is True

    def test_init_with_no_verify_ssl_alias(self, runner, tmp_path):
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init", "--no-verify-ssl"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["no_verify_ssl"] is True

    def test_init_with_env_no_verify_ssl(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("EXCHANGE_NO_VERIFY_SSL", "1")
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["no_verify_ssl"] is True

    def test_init_with_auth_type_flag(self, runner, tmp_path):
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init", "--auth-type", "basic"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["auth_type"] == "basic"

    def test_init_with_env_auth_type(self, runner, tmp_path, monkeypatch):
        monkeypatch.setenv("EXCHANGE_AUTH_TYPE", "basic")
        config_path = str(tmp_path / ".exchange-cli")
        with patch("exchange_cli.commands.config.probe_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\ntest@example.com\n",
            )
        assert result.exit_code == 0
        saved = json.loads((tmp_path / ".exchange-cli" / "config.json").read_text(encoding="utf-8"))
        assert saved["accounts"]["test@example.com"]["auth_type"] == "basic"

    def test_init_aborted_keeps_stdout_valid_json(self, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        result = runner.invoke(
            cli,
            ["--config", str(config_dir), "config", "init"],
            input="",
        )
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["code"] == "ABORTED"

class TestConfigShow:
    def test_show_json(self, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        cm = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cm.save_account("test@example.com", "mail.example.com", "DOMAIN\\test", "secret", "ntlm")
        result = runner.invoke(cli, ["--config", str(tmp_path / ".exchange-cli"), "config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["accounts"]["test@example.com"]["password"] == "********"

    def test_show_no_config(self, runner, tmp_path):
        result = runner.invoke(cli, ["--config", str(tmp_path / "nonexistent"), "config", "show"])
        assert result.exit_code != 0 or "error" in result.output.lower()
