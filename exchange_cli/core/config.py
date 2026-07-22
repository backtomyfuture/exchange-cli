"""Single-account configuration with encrypted credentials and atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .errors import CliError

DEFAULT_CONFIG_DIR = Path.home() / ".exchange-cli"
CONFIG_FILENAME = "config.json"
KEY_FILENAME = ".key"
CONFIG_VERSION = 1
SUPPORTED_AUTH_TYPES = {"ntlm", "basic"}
TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}
DEFAULT_TIMEOUT_SECONDS = 30
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 300
CONFIG_ENV_VARS = (
    "EXCHANGE_SERVER",
    "EXCHANGE_USERNAME",
    "EXCHANGE_PASSWORD",
    "EXCHANGE_AUTH_TYPE",
    "EXCHANGE_NO_VERIFY_SSL",
    "EXCHANGE_DOMAIN",
    "EXCHANGE_EMAIL_SUFFIX",
    "EXCHANGE_EMAIL",
    "EXCHANGE_TIMEOUT_SECONDS",
)


def _fsync_directory(path: Path) -> None:
    """Persist a directory entry where the platform supports directory handles."""
    if os.name == "nt":
        return
    directory_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _secure_file_descriptor(descriptor: int) -> None:
    """Restrict a newly created file on POSIX; Windows uses the user's ACL."""
    if os.name == "nt":
        return
    os.fchmod(descriptor, 0o600)


class ConfigManager:
    def __init__(self, config_dir: Path | str | None = None):
        self.config_dir = Path(config_dir).expanduser() if config_dir else DEFAULT_CONFIG_DIR

    @property
    def config_path(self) -> Path:
        return self.config_dir / CONFIG_FILENAME

    @property
    def key_path(self) -> Path:
        return self.config_dir / KEY_FILENAME

    def _ensure_private_config_dir(self, *, create: bool = True) -> None:
        if self.config_dir.is_symlink():
            raise CliError("Configuration directory must not be a symlink.", code="CONFIG_INVALID")
        if self.config_dir.exists():
            if not self.config_dir.is_dir():
                raise CliError("Configuration path is not a directory.", code="CONFIG_INVALID")
        elif create:
            try:
                self.config_dir.mkdir(mode=0o700, parents=True)
            except OSError as exc:
                raise CliError("Could not create configuration directory.", code="CONFIG_WRITE_FAILED") from exc
        else:
            return
        try:
            self.config_dir.chmod(0o700)
        except OSError as exc:
            raise CliError("Could not secure configuration directory.", code="CONFIG_INVALID") from exc

    def _load_key(self) -> bytes:
        self._ensure_private_config_dir(create=False)
        if self.key_path.is_symlink():
            raise CliError("Configuration key must not be a symlink.", code="CONFIG_INVALID")
        if not self.key_path.exists():
            raise CliError(
                "Configuration encryption key is missing. Run: exchange-cli config init",
                code="CONFIG_KEY_MISSING",
            )
        if not self.key_path.is_file():
            raise CliError("Configuration key is not a regular file.", code="CONFIG_INVALID")
        try:
            self.key_path.chmod(0o600)
            key = self.key_path.read_bytes()
            Fernet(key)
        except (OSError, TypeError, ValueError) as exc:
            raise CliError("Configuration encryption key is invalid.", code="CONFIG_DECRYPT_FAILED") from exc
        return key

    def _get_or_create_key(self) -> bytes:
        self._ensure_private_config_dir()
        if self.key_path.exists() or self.key_path.is_symlink():
            return self._load_key()

        key = Fernet.generate_key()
        try:
            descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._load_key()
        except OSError as exc:
            raise CliError("Could not create configuration key.", code="CONFIG_WRITE_FAILED") from exc

        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(key)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            self.key_path.unlink(missing_ok=True)
            raise CliError("Could not write configuration key.", code="CONFIG_WRITE_FAILED") from exc
        return key

    def _encrypt(self, plaintext: str) -> str:
        return Fernet(self._get_or_create_key()).encrypt(plaintext.encode()).decode()

    def _decrypt(self, token: str) -> str:
        try:
            return Fernet(self._load_key()).decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise CliError("Could not decrypt the stored password.", code="CONFIG_DECRYPT_FAILED") from exc
        except (AttributeError, UnicodeDecodeError) as exc:
            raise CliError("Stored password is invalid.", code="CONFIG_DECRYPT_FAILED") from exc

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

    def _normalize_text(self, value: Any, *, lower: bool = False) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized.lower() if lower else normalized

    def _normalize_server(self, value: Any) -> str | None:
        server = self._normalize_text(value)
        if server is None:
            return None
        if "://" in server or any(character in server for character in "/?#") or any(
            character.isspace() for character in server
        ):
            raise CliError(
                "Exchange server must be a hostname or IP address without a URL scheme or path.",
                code="CONFIG_INVALID",
                exit_code=2,
                details={"field": "server"},
            )
        return server

    def parse_timeout(self, value: Any) -> int:
        if isinstance(value, bool):
            parsed = None
        elif isinstance(value, int):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = int(value.strip())
            except ValueError:
                parsed = None
        else:
            parsed = None
        if parsed is None or not MIN_TIMEOUT_SECONDS <= parsed <= MAX_TIMEOUT_SECONDS:
            raise CliError(
                f"Exchange timeout must be between {MIN_TIMEOUT_SECONDS} and {MAX_TIMEOUT_SECONDS} seconds.",
                code="CONFIG_INVALID",
                exit_code=2,
                details={"field": "timeout_seconds"},
            )
        return parsed

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

    def _validate_config(self, config: Any) -> dict[str, Any]:
        if not isinstance(config, dict):
            raise CliError("Configuration root must be an object.", code="CONFIG_INVALID")

        version = config.get("version", CONFIG_VERSION)
        if type(version) is not int or version != CONFIG_VERSION:
            raise CliError(
                f"Unsupported configuration version: {version!r}.",
                code="CONFIG_UNSUPPORTED_VERSION",
            )

        accounts = config.get("accounts")
        if not isinstance(accounts, dict) or not accounts:
            raise CliError("Configuration must contain exactly one account.", code="CONFIG_INVALID")
        if len(accounts) != 1:
            raise CliError(
                "Multiple accounts are not supported. Run: exchange-cli config init",
                code="MULTIPLE_ACCOUNTS_UNSUPPORTED",
            )

        raw_email, raw_account = next(iter(accounts.items()))
        email = self._normalize_text(raw_email)
        if not email or not isinstance(raw_account, dict):
            raise CliError("Configured account is invalid.", code="CONFIG_INVALID")

        default_account = self._normalize_text(config.get("default_account")) or email
        if default_account.casefold() != email.casefold():
            raise CliError("Default account does not match the configured account.", code="CONFIG_INVALID")

        server = self._normalize_server(raw_account.get("server"))
        username = self._normalize_text(raw_account.get("username"))
        password = raw_account.get("password")
        auth_type = self._normalize_text(raw_account.get("auth_type"), lower=True) or "ntlm"
        no_verify_ssl = raw_account.get("no_verify_ssl", False)
        missing = [
            field
            for field, value in (
                ("email", email),
                ("server", server),
                ("username", username),
                ("password", password if isinstance(password, str) and password else None),
            )
            if value is None
        ]
        if missing:
            raise CliError(
                "Configuration is missing required fields.",
                code="CONFIG_INCOMPLETE",
                details={"missing_fields": missing},
            )
        if auth_type not in SUPPORTED_AUTH_TYPES:
            raise CliError("Configured auth_type is invalid.", code="CONFIG_INVALID")
        if type(no_verify_ssl) is not bool:
            raise CliError("Configured no_verify_ssl must be a boolean.", code="CONFIG_INVALID")

        normalized_account: dict[str, Any] = {
            "server": server,
            "username": username,
            "password": password,
            "auth_type": auth_type,
            "no_verify_ssl": no_verify_ssl,
        }
        if "timeout_seconds" in raw_account:
            normalized_account["timeout_seconds"] = self.parse_timeout(raw_account["timeout_seconds"])
        return {
            "version": CONFIG_VERSION,
            "default_account": email,
            "accounts": {email: normalized_account},
        }

    def load_config(self) -> dict[str, Any] | None:
        if self.config_path.is_symlink():
            raise CliError("Configuration file must not be a symlink.", code="CONFIG_INVALID")
        if not self.config_path.exists():
            return None
        self._ensure_private_config_dir(create=False)
        if not self.config_path.is_file():
            raise CliError("Configuration path is not a regular file.", code="CONFIG_INVALID")
        try:
            self.config_path.chmod(0o600)
            with self.config_path.open(encoding="utf-8") as handle:
                raw_config = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise CliError("Configuration file is unreadable or malformed.", code="CONFIG_INVALID") from exc
        return self._validate_config(raw_config)

    def _atomic_write_json(self, config: dict[str, Any]) -> None:
        self._ensure_private_config_dir()
        descriptor = -1
        temporary_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(prefix=".config.", dir=self.config_dir)
            temporary_path = Path(raw_path)
            _secure_file_descriptor(descriptor)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                json.dump(config, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.config_path)
            self.config_path.chmod(0o600)
            _fsync_directory(self.config_dir)
        except (OSError, TypeError, ValueError) as exc:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise CliError("Could not write configuration atomically.", code="CONFIG_WRITE_FAILED") from exc

    def _save_config(self, config: dict[str, Any]) -> None:
        self._atomic_write_json(self._validate_config(config))

    def save_account(
        self,
        email: str,
        server: str,
        username: str,
        password: str,
        auth_type: str = "ntlm",
        no_verify_ssl: bool = False,
    ) -> None:
        normalized_email = self._normalize_text(email)
        normalized_server = self._normalize_server(server)
        normalized_username = self._normalize_text(username)
        normalized_auth_type = self._normalize_text(auth_type, lower=True) or "ntlm"

        missing = [
            field
            for field, value in (
                ("email", normalized_email),
                ("server", normalized_server),
                ("username", normalized_username),
                ("password", password if isinstance(password, str) and password else None),
            )
            if value is None
        ]
        if missing:
            raise CliError(
                "Account configuration is incomplete.",
                code="CONFIG_INCOMPLETE",
                exit_code=2,
                details={"missing_fields": missing},
            )
        if normalized_auth_type not in SUPPORTED_AUTH_TYPES:
            raise CliError("Unsupported auth type.", code="INVALID_AUTH_TYPE", exit_code=2)
        if type(no_verify_ssl) is not bool:
            raise CliError("no_verify_ssl must be a boolean.", code="CONFIG_INVALID", exit_code=2)

        config = {
            "version": CONFIG_VERSION,
            "default_account": normalized_email,
            "accounts": {
                normalized_email: {
                    "server": normalized_server,
                    "username": normalized_username,
                    "password": self._encrypt(password),
                    "auth_type": normalized_auth_type,
                    "no_verify_ssl": no_verify_ssl,
                }
            },
        }
        self._save_config(config)

    def _env_text(self, name: str, *, lower: bool = False) -> tuple[bool, str | None]:
        if name not in os.environ:
            return False, None
        return True, self._normalize_text(os.environ[name], lower=lower)

    def get_account_credentials(self, email: str | None) -> dict[str, Any] | None:
        config = self.load_config()
        env_configured = any(name in os.environ for name in CONFIG_ENV_VARS)
        if config is None and not env_configured:
            return None

        stored_email: str | None = None
        stored_account: dict[str, Any] = {}
        if config:
            stored_email = config["default_account"]
            stored_account = config["accounts"][stored_email]

        _, env_server = self._env_text("EXCHANGE_SERVER")
        env_server_present = "EXCHANGE_SERVER" in os.environ
        _, env_username = self._env_text("EXCHANGE_USERNAME")
        env_username_present = "EXCHANGE_USERNAME" in os.environ
        env_password_present = "EXCHANGE_PASSWORD" in os.environ
        env_password = os.environ.get("EXCHANGE_PASSWORD")
        _, env_auth = self._env_text("EXCHANGE_AUTH_TYPE", lower=True)
        env_auth_present = "EXCHANGE_AUTH_TYPE" in os.environ
        _, env_domain = self._env_text("EXCHANGE_DOMAIN")
        _, env_email_suffix = self._env_text("EXCHANGE_EMAIL_SUFFIX")
        _, env_email = self._env_text("EXCHANGE_EMAIL")
        env_email_present = "EXCHANGE_EMAIL" in os.environ

        resolved_email = env_email if env_email_present else stored_email
        resolved_server = env_server if env_server_present else stored_account.get("server")
        resolved_username = env_username if env_username_present else stored_account.get("username")
        if not resolved_username:
            resolved_username = self._derive_username_from_email(resolved_email, env_domain)
        if not resolved_email:
            resolved_email = self._derive_email_from_username(resolved_username, env_email_suffix)

        requested_email = self._normalize_text(email)
        if requested_email and resolved_email and requested_email.casefold() != resolved_email.casefold():
            raise CliError(
                "--account does not match the configured single account.",
                code="ACCOUNT_MISMATCH",
                exit_code=2,
                details={"configured_account": resolved_email},
            )

        if env_password_present:
            resolved_password = env_password if env_password else None
        elif stored_account:
            resolved_password = self._decrypt(stored_account["password"])
        else:
            resolved_password = None

        resolved_auth = env_auth if env_auth_present else stored_account.get("auth_type", "ntlm")
        resolved_auth = self._normalize_text(resolved_auth, lower=True) or "ntlm"
        if resolved_auth not in SUPPORTED_AUTH_TYPES:
            raise CliError("Unsupported auth type.", code="INVALID_AUTH_TYPE", exit_code=2)

        if "EXCHANGE_NO_VERIFY_SSL" in os.environ:
            no_verify_ssl = self._parse_bool(os.environ["EXCHANGE_NO_VERIFY_SSL"])
            if no_verify_ssl is None:
                raise CliError(
                    "EXCHANGE_NO_VERIFY_SSL must be a boolean value.",
                    code="CONFIG_INVALID",
                    exit_code=2,
                    details={"field": "no_verify_ssl"},
                )
        else:
            no_verify_ssl = bool(stored_account.get("no_verify_ssl", False))

        if "EXCHANGE_TIMEOUT_SECONDS" in os.environ:
            timeout_seconds = self.parse_timeout(os.environ["EXCHANGE_TIMEOUT_SECONDS"])
        elif "timeout_seconds" in stored_account:
            timeout_seconds = self.parse_timeout(stored_account["timeout_seconds"])
        else:
            timeout_seconds = DEFAULT_TIMEOUT_SECONDS

        resolved_server = self._normalize_server(resolved_server)
        resolved_username = self._normalize_text(resolved_username)
        resolved_email = self._normalize_text(resolved_email)
        missing = [
            field
            for field, value in (
                ("email", resolved_email),
                ("server", resolved_server),
                ("username", resolved_username),
                ("password", resolved_password),
            )
            if value is None
        ]
        if missing:
            raise CliError(
                "Exchange configuration is incomplete.",
                code="CONFIG_INCOMPLETE",
                details={"missing_fields": missing},
            )

        return {
            "email": resolved_email,
            "server": resolved_server,
            "username": resolved_username,
            "password": resolved_password,
            "auth_type": resolved_auth,
            "no_verify_ssl": no_verify_ssl,
            "timeout_seconds": timeout_seconds,
        }

    def get_display_config(self) -> dict[str, Any] | None:
        config = self.load_config()
        if not config:
            return None
        display = json.loads(json.dumps(config))
        for account in display.get("accounts", {}).values():
            account["password"] = "********"
        return display
