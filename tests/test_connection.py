from unittest.mock import patch

import pytest
from exchangelib.protocol import BaseProtocol

from exchange_cli.core.connection import DEFAULT_HTTP_ADAPTER_CLS, ConnectionManager, NoVerifyHTTPAdapter


@pytest.fixture
def cm(tmp_path):
    from exchange_cli.core.config import ConfigManager

    cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
    cfg.save_account("test@example.com", "mail.example.com", "DOMAIN\\test", "pass123", "ntlm")
    return ConnectionManager(cfg)


class TestConnectionManager:
    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_creates_connection(self, mock_account, mock_config, mock_credentials, cm):
        account = cm.get_account()
        mock_credentials.assert_called_once_with("DOMAIN\\test", "pass123")
        mock_config.assert_called_once()
        mock_account.assert_called_once()
        assert mock_account.call_args.kwargs["primary_smtp_address"] == "test@example.com"
        assert account is mock_account.return_value

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_uses_saved_auth_type(self, mock_account, mock_config, mock_credentials, tmp_path):
        from exchange_cli.core.config import ConfigManager

        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cfg.save_account("test@example.com", "mail.example.com", "DOMAIN\\test", "pass123", "basic")
        conn = ConnectionManager(cfg)
        conn.get_account()

        assert mock_config.call_args.kwargs["auth_type"] == "basic"

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_supports_no_verify_ssl_env(self, mock_account, mock_config, mock_credentials, cm, monkeypatch):
        monkeypatch.setenv("EXCHANGE_NO_VERIFY_SSL", "1")
        cm.get_account()
        assert BaseProtocol.HTTP_ADAPTER_CLS is NoVerifyHTTPAdapter

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_supports_no_verify_ssl_from_config(
        self, mock_account, mock_config, mock_credentials, tmp_path
    ):
        from exchange_cli.core.config import ConfigManager

        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cfg.save_account("test@example.com", "mail.example.com", "DOMAIN\\test", "pass123", "ntlm", no_verify_ssl=True)
        conn = ConnectionManager(cfg)
        conn.get_account()
        assert BaseProtocol.HTTP_ADAPTER_CLS is NoVerifyHTTPAdapter

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_uses_default_ssl_adapter_when_env_not_set(
        self, mock_account, mock_config, mock_credentials, cm, monkeypatch
    ):
        monkeypatch.delenv("EXCHANGE_NO_VERIFY_SSL", raising=False)
        cm.get_account()
        assert BaseProtocol.HTTP_ADAPTER_CLS is DEFAULT_HTTP_ADAPTER_CLS

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_caches(self, mock_account, mock_config, mock_credentials, cm):
        account1 = cm.get_account()
        account2 = cm.get_account()
        assert account1 is account2
        assert mock_account.call_count == 1

    def test_get_account_no_config_raises(self, tmp_path):
        from exchange_cli.core.config import ConfigManager

        cfg = ConfigManager(config_dir=tmp_path / ".no-config")
        conn = ConnectionManager(cfg)
        with pytest.raises(SystemExit):
            conn.get_account()

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_env_var_override(self, mock_account, mock_config, mock_credentials, tmp_path, monkeypatch):
        from exchange_cli.core.config import ConfigManager

        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_USERNAME", "envuser")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        conn = ConnectionManager(cfg)
        conn.get_account()
        mock_credentials.assert_called_once_with("envuser", "envpass")
