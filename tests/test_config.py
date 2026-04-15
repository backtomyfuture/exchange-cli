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
            no_verify_ssl=True,
        )
        loaded = cm.load_config()
        assert loaded["default_account"] == "test@example.com"
        acc = loaded["accounts"]["test@example.com"]
        assert acc["server"] == "mail.example.com"
        assert acc["username"] == "DOMAIN\\test"
        assert acc["auth_type"] == "ntlm"
        assert acc["no_verify_ssl"] is True
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
        assert creds["no_verify_ssl"] is False

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

    def test_env_domain_derives_username(self, cm, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        monkeypatch.setenv("EXCHANGE_DOMAIN", "hnanet")
        creds = cm.get_account_credentials("q-fu@tianjin-air.com")
        assert creds["username"] == "hnanet\\q-fu"
        assert creds["email"] == "q-fu@tianjin-air.com"

    def test_env_email_suffix_derives_email(self, cm, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        monkeypatch.setenv("EXCHANGE_USERNAME", "hnanet\\q-fu")
        monkeypatch.setenv("EXCHANGE_EMAIL_SUFFIX", "@tianjin-air.com")
        creds = cm.get_account_credentials(None)
        assert creds["email"] == "q-fu@tianjin-air.com"

    def test_env_no_verify_ssl_overrides_config(self, cm, monkeypatch):
        cm.save_account("test@example.com", "mail.example.com", "user", "pass", "ntlm", no_verify_ssl=False)
        monkeypatch.setenv("EXCHANGE_NO_VERIFY_SSL", "1")
        creds = cm.get_account_credentials("test@example.com")
        assert creds["no_verify_ssl"] is True

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

    def test_save_account_trims_whitespace_inputs(self, cm):
        cm.save_account(
            email="  test@example.com\t",
            server="\t10.72.8.110 ",
            username=" hnanet\\q-fu ",
            password="secret",
            auth_type=" ntlm ",
        )
        creds = cm.get_account_credentials("test@example.com")
        assert creds["email"] == "test@example.com"
        assert creds["server"] == "10.72.8.110"
        assert creds["username"] == "hnanet\\q-fu"
        assert creds["auth_type"] == "ntlm"

    def test_get_account_credentials_trims_legacy_stored_whitespace(self, cm):
        cm._save_config(
            {
                "version": 1,
                "default_account": "test@example.com",
                "accounts": {
                    "test@example.com": {
                        "server": "\t10.72.8.110 ",
                        "username": " hnanet\\q-fu ",
                        "password": cm._encrypt("secret"),
                        "auth_type": " ntlm ",
                        "no_verify_ssl": False,
                    }
                },
            }
        )
        creds = cm.get_account_credentials("test@example.com")
        assert creds["server"] == "10.72.8.110"
        assert creds["username"] == "hnanet\\q-fu"
        assert creds["auth_type"] == "ntlm"
