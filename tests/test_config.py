import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from exchange_cli.core.config import ConfigManager, _fsync_directory, _secure_file_descriptor
from exchange_cli.core.errors import CliError


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
        monkeypatch.setenv("EXCHANGE_EMAIL", "env@example.com")
        creds = cm.get_account_credentials(None)
        assert creds["server"] == "env.example.com"
        assert creds["username"] == "envuser"
        assert creds["password"] == "envpass"
        assert creds["auth_type"] == "basic"
        assert creds["no_verify_ssl"] is False
        assert creds["email"] == "env@example.com"
        assert creds["timeout_seconds"] == 30

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
        monkeypatch.setenv("EXCHANGE_EMAIL", "q-fu@tianjin-air.com")
        creds = cm.get_account_credentials(None)
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

    def test_second_save_replaces_single_account(self, cm):
        cm.save_account("a@x.com", "s1.com", "u1", "p1", "ntlm")
        cm.save_account("b@x.com", "s2.com", "u2", "p2", "basic")
        config = cm.load_config()
        assert list(config["accounts"]) == ["b@x.com"]
        assert config["default_account"] == "b@x.com"

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

    def test_rejects_legacy_multiple_accounts(self, cm):
        first_password = cm._encrypt("first")
        second_password = cm._encrypt("second")
        cm.config_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_account": "a@x.com",
                    "accounts": {
                        "a@x.com": {
                            "server": "s1.com",
                            "username": "u1",
                            "password": first_password,
                            "auth_type": "ntlm",
                            "no_verify_ssl": False,
                        },
                        "b@x.com": {
                            "server": "s2.com",
                            "username": "u2",
                            "password": second_password,
                            "auth_type": "basic",
                            "no_verify_ssl": False,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(CliError) as caught:
            cm.load_config()

        assert caught.value.code == "MULTIPLE_ACCOUNTS_UNSUPPORTED"

    def test_normalizes_single_legacy_account(self, cm):
        password = cm._encrypt("secret")
        cm.config_path.write_text(
            json.dumps(
                {
                    "default_account": " TEST@EXAMPLE.COM ",
                    "accounts": {
                        " test@example.com ": {
                            "server": " mail.example.com ",
                            "username": " user ",
                            "password": password,
                            "auth_type": " NTLM ",
                            "no_verify_ssl": False,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        config = cm.load_config()

        assert config["version"] == 1
        assert config["default_account"] == "test@example.com"
        assert list(config["accounts"]) == ["test@example.com"]

    def test_rejects_future_config_version(self, cm):
        cm.config_dir.mkdir(mode=0o700)
        cm.config_path.write_text(json.dumps({"version": 2, "accounts": {}}), encoding="utf-8")

        with pytest.raises(CliError) as caught:
            cm.load_config()

        assert caught.value.code == "CONFIG_UNSUPPORTED_VERSION"

    def test_malformed_json_is_config_invalid(self, cm):
        cm.config_dir.mkdir(mode=0o700)
        cm.config_path.write_text("{broken", encoding="utf-8")

        with pytest.raises(CliError) as caught:
            cm.load_config()

        assert caught.value.code == "CONFIG_INVALID"

    def test_missing_key_does_not_create_new_key(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        cm.key_path.unlink()

        with pytest.raises(CliError) as caught:
            cm.get_account_credentials(None)

        assert caught.value.code == "CONFIG_KEY_MISSING"
        assert not cm.key_path.exists()

    def test_corrupt_key_returns_decrypt_error(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        cm.key_path.write_bytes(b"not-a-fernet-key")

        with pytest.raises(CliError) as caught:
            cm.get_account_credentials(None)

        assert caught.value.code == "CONFIG_DECRYPT_FAILED"

    def test_config_write_is_atomic(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "first", "ntlm")
        original = cm.config_path.read_bytes()

        with patch("exchange_cli.core.config.os.replace", side_effect=OSError("disk failure")):
            with pytest.raises(CliError) as caught:
                cm.save_account("b@x.com", "s2.com", "u2", "second", "ntlm")

        assert caught.value.code == "CONFIG_WRITE_FAILED"
        assert cm.config_path.read_bytes() == original

    def test_directory_fsync_is_skipped_on_windows(self, tmp_path):
        with (
            patch("exchange_cli.core.config.os.name", "nt"),
            patch("exchange_cli.core.config.os.open") as open_mock,
        ):
            _fsync_directory(tmp_path)

        open_mock.assert_not_called()

    def test_file_descriptor_chmod_is_skipped_on_windows(self):
        with (
            patch("exchange_cli.core.config.os.name", "nt"),
            patch("exchange_cli.core.config.os.fchmod") as fchmod_mock,
        ):
            _secure_file_descriptor(123)

        fchmod_mock.assert_not_called()

    def test_private_directory_and_file_modes(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")

        assert stat.S_IMODE(cm.config_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(cm.config_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(cm.key_path.stat().st_mode) == 0o600

    def test_partial_env_overrides_keep_stored_email(self, cm, monkeypatch):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        monkeypatch.setenv("EXCHANGE_SERVER", "override.example.com")

        credentials = cm.get_account_credentials(None)

        assert credentials["email"] == "a@x.com"
        assert credentials["server"] == "override.example.com"
        assert credentials["username"] == "u"
        assert credentials["password"] == "secret"

    def test_incomplete_env_reports_missing_fields(self, cm, monkeypatch):
        monkeypatch.setenv("EXCHANGE_SERVER", "mail.example.com")

        with pytest.raises(CliError) as caught:
            cm.get_account_credentials(None)

        assert caught.value.code == "CONFIG_INCOMPLETE"
        assert set(caught.value.details["missing_fields"]) == {"email", "username", "password"}

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("EXCHANGE_NO_VERIFY_SSL", "sometimes"),
            ("EXCHANGE_TIMEOUT_SECONDS", "0"),
            ("EXCHANGE_TIMEOUT_SECONDS", "301"),
            ("EXCHANGE_TIMEOUT_SECONDS", "slow"),
        ],
    )
    def test_invalid_env_bool_and_timeout(self, cm, monkeypatch, name, value):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        monkeypatch.setenv(name, value)

        with pytest.raises(CliError) as caught:
            cm.get_account_credentials(None)

        assert caught.value.code == "CONFIG_INVALID"

    def test_account_assertion_is_case_insensitive(self, cm):
        cm.save_account("User@Example.com", "s.com", "u", "secret", "ntlm")

        credentials = cm.get_account_credentials(" user@example.COM ")

        assert credentials["email"] == "User@Example.com"

    def test_account_mismatch_is_rejected(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")

        with pytest.raises(CliError) as caught:
            cm.get_account_credentials("b@x.com")

        assert caught.value.code == "ACCOUNT_MISMATCH"

    def test_server_rejects_url(self, cm):
        with pytest.raises(CliError) as caught:
            cm.save_account("a@x.com", "https://mail.example.com/EWS", "u", "secret", "ntlm")

        assert caught.value.code == "CONFIG_INVALID"
