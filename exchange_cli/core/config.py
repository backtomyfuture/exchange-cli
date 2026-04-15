"""Configuration management - read/write config and encrypt passwords."""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULT_CONFIG_DIR = Path.home() / ".exchange-cli"
CONFIG_FILENAME = "config.json"
KEY_FILENAME = ".key"


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
    ) -> None:
        config = self.load_config() or {"version": 1, "default_account": email, "accounts": {}}
        config["accounts"][email] = {
            "server": server,
            "username": username,
            "password": self._encrypt(password),
            "auth_type": auth_type,
        }
        if not config.get("default_account"):
            config["default_account"] = email
        self._save_config(config)

    def get_account_credentials(self, email: str | None) -> dict | None:
        env_server = os.environ.get("EXCHANGE_SERVER")
        env_username = os.environ.get("EXCHANGE_USERNAME")
        env_password = os.environ.get("EXCHANGE_PASSWORD")
        env_auth = os.environ.get("EXCHANGE_AUTH_TYPE")

        if env_server and env_username and env_password:
            return {
                "server": env_server,
                "username": env_username,
                "password": env_password,
                "auth_type": env_auth or "ntlm",
            }

        config = self.load_config()
        if not config:
            return None

        target = email or config.get("default_account")
        accounts = config.get("accounts", {})
        if not target or target not in accounts:
            return None

        account = accounts[target]
        return {
            "server": env_server or account["server"],
            "username": env_username or account["username"],
            "password": env_password or self._decrypt(account["password"]),
            "auth_type": env_auth or account.get("auth_type", "ntlm"),
        }

    def get_display_config(self) -> dict | None:
        config = self.load_config()
        if not config:
            return None
        display = json.loads(json.dumps(config))
        for account in display.get("accounts", {}).values():
            account["password"] = "********"
        return display
