from unittest.mock import patch

import pytest
from exchangelib.protocol import BaseProtocol, FailFast

from exchange_cli.core.connection import DEFAULT_HTTP_ADAPTER_CLS, ConnectionManager, NoVerifyHTTPAdapter
from exchange_cli.core.errors import CliError


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
        assert mock_account.call_args.kwargs["autodiscover"] is False
        assert isinstance(mock_config.call_args.kwargs["retry_policy"], FailFast)
        assert mock_config.call_args.kwargs["max_connections"] == 1
        assert BaseProtocol.TIMEOUT == 30
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
        with pytest.raises(CliError) as exc_info:
            conn.get_account()
        assert exc_info.value.code == "CONFIG_NOT_FOUND"
        assert exc_info.value.retryable is False

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_env_var_override(self, mock_account, mock_config, mock_credentials, tmp_path, monkeypatch):
        from exchange_cli.core.config import ConfigManager

        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_USERNAME", "envuser")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        monkeypatch.setenv("EXCHANGE_EMAIL", "env@example.com")
        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        conn = ConnectionManager(cfg)
        conn.get_account()
        mock_credentials.assert_called_once_with("envuser", "envpass")

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_uses_canonical_primary_smtp_address(self, mock_account, mock_config, mock_credentials, cm):
        cm.get_account(" TEST@EXAMPLE.COM ")

        assert mock_account.call_args.kwargs["primary_smtp_address"] == "test@example.com"

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_applies_bounded_http_timeout(
        self, mock_account, mock_config, mock_credentials, cm, monkeypatch
    ):
        monkeypatch.setenv("EXCHANGE_TIMEOUT_SECONDS", "45")

        cm.get_account()

        assert BaseProtocol.TIMEOUT == 45

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_cache_invalidates_after_config_change(
        self, mock_account, mock_config, mock_credentials, tmp_path, monkeypatch
    ):
        from exchange_cli.core.config import ConfigManager

        first = mock_account.return_value
        second = type(first)()
        mock_account.side_effect = [first, second]
        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        cfg.save_account("test@example.com", "mail.example.com", "user", "first", "ntlm")
        connection = ConnectionManager(cfg)

        assert connection.get_account() is first
        monkeypatch.setenv("EXCHANGE_PASSWORD", "second")
        assert connection.get_account() is second
        assert mock_account.call_count == 2
        first.protocol.close.assert_called_once()

    @patch("exchange_cli.core.connection.Credentials", side_effect=ValueError("invalid username"))
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_non_auth_value_error_is_not_invalid_auth_type(
        self, mock_account, mock_config, mock_credentials, cm
    ):
        with pytest.raises(CliError) as caught:
            cm.get_account()

        assert caught.value.code == "CONFIG_INVALID"
