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
        with patch("exchange_cli.commands.config._test_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", config_path, "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\nntlm\ntest@example.com\nn\n",
            )
        assert result.exit_code == 0
        assert "saved" in result.output.lower() or "ok" in result.output.lower()

    def test_init_overwrites_instead_of_adding(self, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        config_dir = tmp_path / ".exchange-cli"
        manager = ConfigManager(config_dir=config_dir)
        manager.save_account("old@example.com", "old.example.com", "old", "oldpass", "ntlm")
        with patch("exchange_cli.commands.config._test_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="y\nmail.example.com\nDOMAIN\\test\nsecret123\nntlm\ntest@example.com\nn\n",
            )

        assert result.exit_code == 0
        assert list(manager.load_config()["accounts"]) == ["test@example.com"]

    def test_failed_probe_does_not_save_without_confirmation(self, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        with patch(
            "exchange_cli.commands.config._test_connection",
            side_effect=CliError("Authentication failed", code="AUTH_ERROR"),
        ):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="mail.example.com\nDOMAIN\\test\nsecret123\nntlm\ntest@example.com\nn\nn\n",
            )

        assert result.exit_code == 0
        assert not (config_dir / "config.json").exists()
        assert '"changed": false' in result.stdout.lower()

    def test_init_can_recover_corrupt_config(self, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        config_dir.mkdir()
        (config_dir / "config.json").write_text("{broken", encoding="utf-8")
        with patch("exchange_cli.commands.config._test_connection", return_value=True):
            result = runner.invoke(
                cli,
                ["--config", str(config_dir), "config", "init"],
                input="y\nmail.example.com\nDOMAIN\\test\nsecret123\nntlm\ntest@example.com\nn\n",
            )

        assert result.exit_code == 0
        assert json.loads((config_dir / "config.json").read_text(encoding="utf-8"))["version"] == 1

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


class TestConfigTest:
    @patch("exchange_cli.commands.config._test_connection", return_value=True)
    def test_connection_success(self, mock_test, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        cm = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cm.save_account("test@example.com", "mail.example.com", "user", "pass", "ntlm")
        result = runner.invoke(cli, ["--config", str(tmp_path / ".exchange-cli"), "config", "test"])
        assert result.exit_code == 0
        mock_test.assert_called_once_with(
            "mail.example.com", "user", "pass", "ntlm", "test@example.com", False, 30
        )

    @patch("exchange_cli.commands.config._test_connection", return_value=True)
    def test_connection_passes_auth_type(self, mock_test, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        cm = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cm.save_account("test@example.com", "mail.example.com", "user", "pass", "basic")
        result = runner.invoke(cli, ["--config", str(tmp_path / ".exchange-cli"), "config", "test"])
        assert result.exit_code == 0
        mock_test.assert_called_once_with(
            "mail.example.com", "user", "pass", "basic", "test@example.com", False, 30
        )

    @patch(
        "exchange_cli.commands.config._test_connection",
        side_effect=CliError("Authentication failed", code="AUTH_ERROR"),
    )
    def test_config_test_preserves_auth_error(self, mock_test, runner, tmp_path):
        from exchange_cli.core.config import ConfigManager

        manager = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        manager.save_account("test@example.com", "mail.example.com", "user", "pass", "ntlm")

        result = runner.invoke(cli, ["--config", str(manager.config_dir), "config", "test"])

        assert result.exit_code == 1
        assert json.loads(result.stdout)["code"] == "AUTH_ERROR"
