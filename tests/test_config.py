from pathlib import Path

import pytest

from exchange_cli.core.config import ConfigManager


@pytest.fixture
def config_dir(tmp_path):
    return tmp_path / ".exchange-cli"


@pytest.fixture
def cm(config_dir):
    return ConfigManager(config_dir=config_dir)


class TestConfigManager:
    def test_default_config_dir(self):
        cm = ConfigManager()
        assert cm.config_dir == Path.home() / ".exchange-cli"

    def test_save_and_load_account(self, cm):
        cm.save_account(
            email="test@example.com",
            server="mail.example.com",
            username="DOMAIN\\test",
            password="secret123",
            auth_type="ntlm",
        )
        loaded = cm.load_config()
        assert loaded["default_account"] == "test@example.com"
        acc = loaded["accounts"]["test@example.com"]
        assert acc["server"] == "mail.example.com"
        assert acc["username"] == "DOMAIN\\test"
        assert acc["auth_type"] == "ntlm"
        assert acc["password"] != "secret123"
        assert acc["password"].startswith("gAAAAA")

    def test_decrypt_password(self, cm):
        cm.save_account(
            email="test@example.com",
            server="mail.example.com",
            username="test",
            password="mysecret",
            auth_type="ntlm",
        )
        decrypted = cm.get_account_credentials("test@example.com")
        assert decrypted["password"] == "mysecret"

    def test_load_nonexistent_config(self, cm):
        result = cm.load_config()
        assert result is None

    def test_env_var_override(self, cm, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_USERNAME", "envuser")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        monkeypatch.setenv("EXCHANGE_AUTH_TYPE", "basic")
        creds = cm.get_account_credentials(None)
        assert creds["server"] == "env.example.com"
        assert creds["username"] == "envuser"
        assert creds["password"] == "envpass"
        assert creds["auth_type"] == "basic"

    def test_env_vars_override_config_file(self, cm, monkeypatch):
        cm.save_account(
            email="test@example.com",
            server="file.example.com",
            username="fileuser",
            password="filepass",
            auth_type="ntlm",
        )
        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_USERNAME", "envuser")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        creds = cm.get_account_credentials("test@example.com")
        assert creds["server"] == "env.example.com"
        assert creds["username"] == "envuser"
        assert creds["password"] == "envpass"

    def test_multiple_accounts(self, cm):
        cm.save_account("a@x.com", "s1.com", "u1", "p1", "ntlm")
        cm.save_account("b@x.com", "s2.com", "u2", "p2", "basic")
        config = cm.load_config()
        assert len(config["accounts"]) == 2
        assert config["default_account"] == "a@x.com"

    def test_show_config_masks_password(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        display = cm.get_display_config()
        assert display["accounts"]["a@x.com"]["password"] == "********"
