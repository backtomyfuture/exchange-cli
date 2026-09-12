import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from exchange_cli.core.config import ConfigManager
from exchange_cli.core.errors import CliError
from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def _config_dir(tmp_path, *, no_verify_ssl=False):
    config_dir = tmp_path / ".exchange-cli"
    ConfigManager(config_dir=config_dir).save_account(
        "test@example.com",
        "mail.example.com",
        "DOMAIN\\test",
        "pass",
        "ntlm",
        no_verify_ssl=no_verify_ssl,
    )
    return config_dir


class TestDoctor:
    @patch("exchange_cli.commands.doctor.probe_connection", return_value=True)
    def test_reports_config_tls_and_ews_checks(self, mock_probe, runner, tmp_path):
        config_dir = _config_dir(tmp_path)

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["data"]["overall"] == "pass"
        assert data["data"]["checks"] == [
            {"id": "effective_config", "status": "pass"},
            {"id": "tls_verification", "status": "pass"},
            {"id": "ews_root", "status": "pass"},
        ]
        mock_probe.assert_called_once_with(
            {
                "email": "test@example.com",
                "server": "mail.example.com",
                "username": "DOMAIN\\test",
                "password": "pass",
                "auth_type": "ntlm",
                "no_verify_ssl": False,
                "timeout_seconds": 30,
            }
        )

    @patch("exchange_cli.commands.doctor.probe_connection", return_value=True)
    def test_fails_when_tls_verification_is_disabled(self, mock_probe, runner, tmp_path):
        config_dir = _config_dir(tmp_path, no_verify_ssl=True)

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["code"] == "INSECURE_TLS"
        assert data["retryable"] is False
        assert "request_id" in data
        assert "meta" in data and "elapsed_ms" in data["meta"]
        assert data["data"]["overall"] == "fail"
        assert data["data"]["checks"][1]["id"] == "tls_verification"
        assert data["data"]["checks"][1]["status"] == "fail"
        assert data["data"]["checks"][1]["code"] == "INSECURE_TLS"
        mock_probe.assert_called_once()

    @patch("exchange_cli.commands.doctor.probe_connection", return_value=True)
    def test_fails_when_ca_bundle_does_not_exist(self, mock_probe, runner, tmp_path):
        config_dir = tmp_path / ".exchange-cli"
        ConfigManager(config_dir=config_dir).save_account(
            "test@example.com",
            "mail.example.com",
            "DOMAIN\\test",
            "pass",
            "ntlm",
            no_verify_ssl=False,
            ca_bundle=str(tmp_path / "nonexistent-ca.pem"),
        )

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["code"] == "CA_BUNDLE_NOT_FOUND"
        assert data["data"]["overall"] == "fail"
        assert data["data"]["checks"][1]["id"] == "tls_verification"
        assert data["data"]["checks"][1]["status"] == "fail"

    @patch("exchange_cli.commands.doctor.probe_connection", return_value=True)
    def test_passes_when_ca_bundle_exists(self, mock_probe, runner, tmp_path):
        ca_file = tmp_path / "corp-ca.pem"
        ca_file.write_text("dummy cert", encoding="utf-8")
        config_dir = tmp_path / ".exchange-cli"
        ConfigManager(config_dir=config_dir).save_account(
            "test@example.com",
            "mail.example.com",
            "DOMAIN\\test",
            "pass",
            "ntlm",
            no_verify_ssl=False,
            ca_bundle=str(ca_file),
        )

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["data"]["overall"] == "pass"
        assert data["data"]["checks"][1]["id"] == "tls_verification"
        assert data["data"]["checks"][1]["status"] == "pass"

    @patch("exchange_cli.commands.doctor.probe_connection")
    def test_offline_skips_ews_probe(self, mock_probe, runner, tmp_path):
        config_dir = _config_dir(tmp_path)

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor", "--offline"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["data"]["overall"] == "pass"
        assert data["data"]["checks"][2] == {
            "id": "ews_root",
            "status": "skipped",
            "message": "Skipped because --offline was requested.",
        }
        mock_probe.assert_not_called()

    @patch(
        "exchange_cli.commands.doctor.probe_connection",
        side_effect=CliError("Authentication failed", code="AUTH_ERROR"),
    )
    def test_preserves_ews_error_and_reports_failed_check(self, mock_probe, runner, tmp_path):
        config_dir = _config_dir(tmp_path)

        result = runner.invoke(cli, ["--config", str(config_dir), "doctor"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["code"] == "AUTH_ERROR"
        assert data["data"]["overall"] == "fail"
        assert data["data"]["checks"][2] == {
            "id": "ews_root",
            "status": "fail",
            "message": "Authentication failed",
            "code": "AUTH_ERROR",
            "remediation": "Verify the configured credentials with your Exchange administrator.",
        }
        mock_probe.assert_called_once()

    def test_replaces_config_test_and_is_listed_at_the_top_level(self, runner):
        config_help = runner.invoke(cli, ["config", "--help"])
        retired_command = runner.invoke(cli, ["config", "test"])
        root_help = runner.invoke(cli, ["--help"])

        assert config_help.exit_code == 0
        assert "\n  test" not in config_help.output
        assert retired_command.exit_code == 2
        assert json.loads(retired_command.stdout)["code"] == "INVALID_INPUT"
        assert root_help.exit_code == 0
        assert "\n  doctor" in root_help.output
