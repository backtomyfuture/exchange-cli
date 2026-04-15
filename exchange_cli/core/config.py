"""Configuration management - read/write config and encrypt passwords."""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULT_CONFIG_DIR = Path.home() / ".exchange-cli"
CONFIG_FILENAME = "config.json"
KEY_FILENAME = ".key"
TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}


class ConfigManager:
    def __init__(self, config_dir: Path | str | None = None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    @property
    def key_path(self) -> Path:
        return self.config_dir / KEY_FILENAME

    def _get_or_create_key(self) -> bytes:
        if self.key_path.exists():
            return self.key_path.read_bytes()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        self.key_path.write_bytes(key)
        self.key_path.chmod(0o600)
        return key

    def _encrypt(self, plaintext: str) -> str:
        return Fernet(self._get_or_create_key()).encrypt(plaintext.encode()).decode()

    def _decrypt(self, token: str) -> str:
        return Fernet(self._get_or_create_key()).decrypt(token.encode()).decode()

    def _parse_bool(self, value: str | bool | None) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized in TRUTHY_VALUES:
            return True
        if normalized in FALSY_VALUES:
            return False
        return None

    def _derive_username_from_email(self, email: str | None, domain: str | None) -> str | None:
        if not email or not domain:
            return None
        local_part = email.split("@", 1)[0].strip()
        domain = domain.strip()
        if not local_part or not domain:
            return None
        return f"{domain}\\{local_part}"

    def _derive_email_from_username(self, username: str | None, email_suffix: str | None) -> str | None:
        if not username or not email_suffix:
            return None
        suffix = email_suffix if email_suffix.startswith("@") else f"@{email_suffix}"
        local_part = username.split("\\")[-1].strip()
        if "@" in local_part:
            local_part = local_part.split("@", 1)[0]
        if not local_part:
            return None
        return f"{local_part}{suffix}"

    def load_config(self) -> dict | None:
        if not self.config_path.exists():
            return None
        with self.config_path.open(encoding="utf-8") as handle:
            return json.load(handle)

    def _save_config(self, config: dict) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
        self.config_path.chmod(0o600)

    def save_account(
        self,
        email: str,
        server: str,
        username: str,
        password: str,
        auth_type: str = "ntlm",
        no_verify_ssl: bool = False,
    ) -> None:
        config = self.load_config() or {"version": 1, "default_account": email, "accounts": {}}
        config["accounts"][email] = {
            "server": server,
            "username": username,
            "password": self._encrypt(password),
            "auth_type": auth_type,
            "no_verify_ssl": bool(no_verify_ssl),
        }
        if not config.get("default_account"):
            config["default_account"] = email
        self._save_config(config)

    def get_account_credentials(self, email: str | None) -> dict | None:
        env_server = os.environ.get("EXCHANGE_SERVER")
        env_username = os.environ.get("EXCHANGE_USERNAME")
        env_password = os.environ.get("EXCHANGE_PASSWORD")
        env_auth = os.environ.get("EXCHANGE_AUTH_TYPE")
        env_domain = os.environ.get("EXCHANGE_DOMAIN")
        env_email_suffix = os.environ.get("EXCHANGE_EMAIL_SUFFIX")
        env_email = os.environ.get("EXCHANGE_EMAIL")
        env_no_verify_ssl = self._parse_bool(os.environ.get("EXCHANGE_NO_VERIFY_SSL"))

        requested_email = email or env_email

        if env_server and env_password and (env_username or env_domain):
            resolved_email = requested_email
            resolved_username = env_username or self._derive_username_from_email(resolved_email, env_domain)
            if not resolved_email:
                resolved_email = self._derive_email_from_username(resolved_username, env_email_suffix)
            if not resolved_username:
                return None
            return {
                "email": resolved_email,
                "server": env_server,
                "username": resolved_username,
                "password": env_password,
                "auth_type": env_auth or "ntlm",
                "no_verify_ssl": env_no_verify_ssl if env_no_verify_ssl is not None else False,
            }

        config = self.load_config()
        if not config:
            return None

        target = email or config.get("default_account")
        accounts = config.get("accounts", {})
        if not target or target not in accounts:
            return None

        account = accounts[target]
        resolved_email = target
        resolved_username = env_username or account.get("username")
        if not resolved_username:
            resolved_username = self._derive_username_from_email(resolved_email, env_domain)
        if not resolved_email:
            resolved_email = env_email or self._derive_email_from_username(resolved_username, env_email_suffix)

        stored_no_verify = self._parse_bool(account.get("no_verify_ssl"))
        no_verify_ssl = env_no_verify_ssl if env_no_verify_ssl is not None else (stored_no_verify or False)

        return {
            "email": resolved_email,
            "server": env_server or account["server"],
            "username": resolved_username,
            "password": env_password or self._decrypt(account["password"]),
            "auth_type": env_auth or account.get("auth_type", "ntlm"),
            "no_verify_ssl": no_verify_ssl,
        }

    def get_display_config(self) -> dict | None:
        config = self.load_config()
        if not config:
            return None
        display = json.loads(json.dumps(config))
        for account in display.get("accounts", {}).values():
            account["password"] = "********"
        return display
