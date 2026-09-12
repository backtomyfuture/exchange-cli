# exchange-cli Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight, AI-agent-friendly CLI tool for Microsoft Exchange Web Services, wrapping exchangelib with Click commands, JSON-first output, and pip+npm dual distribution.

**Architecture:** Nested command groups (`exchange-cli <resource> <action>`) using Click. Core layer manages config (encrypted JSON file), connection (lazy exchangelib Account), and output (JSON/text formatter). Each command group is a separate module under `commands/`.

**Tech Stack:** Python 3.10+, Click 8.x, exchangelib 5.x, cryptography (Fernet), pytest, ruff

**Spec:** `docs/superpowers/specs/2026-04-15-exchange-cli-design.md`

---

## File Structure

```
exchange-cli/                      # NEW repo root (replaces current exchangelib structure)
├── exchange_cli/
│   ├── __init__.py                # __version__ = "0.1.0"
│   ├── main.py                    # Click group, global options, register command groups
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── config.py              # config {init,show,test}
│   │   ├── email.py               # email {list,read,send,reply,forward,search}
│   │   ├── draft.py               # draft {list,create,send,delete}
│   │   ├── folder.py              # folder {list,tree}
│   │   ├── calendar.py            # calendar {list,create,update,delete}
│   │   ├── task.py                # task {list,create,update,complete,delete}
│   │   └── contact.py             # contact {list,search}
│   └── core/
│       ├── __init__.py
│       ├── config.py              # Config read/write, encryption key mgmt
│       ├── connection.py          # ConnectionManager wrapping exchangelib
│       ├── output.py              # OutputFormatter (JSON/text)
│       └── serializers.py         # exchangelib objects -> dicts
├── tests/
│   ├── conftest.py                # Shared fixtures, mock account factory
│   ├── test_config.py
│   ├── test_connection.py
│   ├── test_output.py
│   ├── test_serializers.py
│   ├── test_email.py
│   ├── test_draft.py
│   ├── test_folder.py
│   ├── test_calendar.py
│   ├── test_task.py
│   └── test_contact.py
├── npm/
│   ├── exchange-cli/
│   │   ├── package.json
│   │   ├── install.js
│   │   └── bin/
│   │       └── exchange-cli.js
│   └── platforms/
│       └── darwin-arm64/
│           └── package.json
├── skills/
│   └── SKILL.md                   # Droid skill for AI agents
├── pyproject.toml
├── README.md
├── LICENSE
└── .github/
    └── workflows/
        ├── test.yml
        └── release.yml
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `exchange_cli/__init__.py`
- Create: `exchange_cli/main.py`
- Create: `exchange_cli/commands/__init__.py`
- Create: `exchange_cli/core/__init__.py`
- Create: `pyproject.toml`
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize new git repo and create project files**

Create a new directory for the project and initialize git:

```bash
mkdir -p /Users/jarod/Documents/exchange-cli
cd /Users/jarod/Documents/exchange-cli
git init
```

- [ ] **Step 2: Create pyproject.toml**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "exchange-cli"
version = "0.1.0"
description = "CLI for Microsoft Exchange Web Services — designed for AI agents"
readme = "README.md"
requires-python = ">=3.10"
license = "Apache-2.0"
keywords = ["exchange", "ews", "cli", "email", "ai-agent", "office365"]
authors = [
    {name = "Jarod"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Topic :: Communications :: Email",
    "Programming Language :: Python :: 3",
]
dependencies = [
    "click>=8.1,<9",
    "exchangelib>=5.0",
    "cryptography>=41.0",
]

[project.scripts]
exchange-cli = "exchange_cli.main:cli"

[project.urls]
Homepage = "https://github.com/canghe/exchange-cli"
Issues = "https://github.com/canghe/exchange-cli/issues"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "ruff>=0.4",
]

[tool.ruff]
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "W"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
```

- [ ] **Step 3: Create exchange_cli/__init__.py**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create exchange_cli/main.py with empty Click group**

```python
import sys

import click

from . import __version__

_CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(context_settings=_CONTEXT_SETTINGS)
@click.version_option(version=__version__, prog_name="exchange-cli")
@click.option("--format", "fmt", default="json", type=click.Choice(["json", "text"]), help="Output format (default: json)")
@click.option("--config", "config_path", default=None, envvar="EXCHANGE_CLI_CONFIG", help="Config file path")
@click.option("--account", "account_email", default=None, help="Account email (overrides default)")
@click.option("--verbose", is_flag=True, default=False, help="Verbose output to stderr")
@click.pass_context
def cli(ctx, fmt, config_path, account_email, verbose):
    """exchange-cli — Exchange Web Services CLI for AI agents

    \b
    Quick start:
      exchange-cli config init          # Interactive setup
      exchange-cli email list           # List inbox messages
      exchange-cli email read MSG_ID    # Read a message
      exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
    """
    ctx.ensure_object(dict)
    ctx.obj["fmt"] = fmt
    ctx.obj["config_path"] = config_path
    ctx.obj["account_email"] = account_email
    ctx.obj["verbose"] = verbose


def main():
    cli()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create empty __init__.py files**

Create `exchange_cli/commands/__init__.py` and `exchange_cli/core/__init__.py` as empty files.

- [ ] **Step 6: Create .gitignore**

```
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.venv/
.pytest_cache/
.ruff_cache/
*.egg
.DS_Store
```

- [ ] **Step 7: Create LICENSE**

Create `LICENSE` with Apache 2.0 text. Use the standard Apache-2.0 license header with author "Jarod".

- [ ] **Step 8: Create tests/conftest.py with shared fixtures**

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def invoke(runner):
    """Shortcut: invoke(args_list) -> click Result."""
    def _invoke(args, **kwargs):
        return runner.invoke(cli, args, catch_exceptions=False, **kwargs)
    return _invoke


@pytest.fixture
def mock_account():
    """A MagicMock pretending to be an exchangelib Account."""
    account = MagicMock()
    account.primary_smtp_address = "test@example.com"
    account.inbox = MagicMock()
    account.sent = MagicMock()
    account.drafts = MagicMock()
    account.trash = MagicMock()
    account.junk = MagicMock()
    account.calendar = MagicMock()
    account.tasks = MagicMock()
    account.contacts = MagicMock()
    account.root = MagicMock()
    return account


def parse_json(result):
    """Parse JSON from CLI output, assert exit code 0."""
    assert result.exit_code == 0, f"CLI failed: {result.output}"
    return json.loads(result.output)
```

- [ ] **Step 9: Verify scaffolding works**

```bash
cd /Users/jarod/Documents/exchange-cli
python3 -m pip install -e ".[dev]"
python3 -m exchange_cli.main --version
python3 -m exchange_cli.main --help
pytest tests/ -v
```

Expected: `--version` prints `exchange-cli, version 0.1.0`, `--help` shows group help, pytest passes (0 tests collected, no errors).

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with Click group and pyproject.toml"
```

---

### Task 2: Core — Config Module

**Files:**
- Create: `exchange_cli/core/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for config module**

Create `tests/test_config.py`:

```python
import json
import os
from pathlib import Path

import pytest

from exchange_cli.core.config import (
    ConfigManager,
    DEFAULT_CONFIG_DIR,
)


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

    def test_save_and_load_account(self, cm, config_dir):
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
        # Password should be encrypted, not plaintext
        assert acc["password"] != "secret123"
        assert acc["password"].startswith("gAAAAA")  # Fernet token prefix

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
        assert config["default_account"] == "a@x.com"  # first added is default

    def test_show_config_masks_password(self, cm):
        cm.save_account("a@x.com", "s.com", "u", "secret", "ntlm")
        display = cm.get_display_config()
        assert display["accounts"]["a@x.com"]["password"] == "********"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: ImportError — `exchange_cli.core.config` doesn't exist yet.

- [ ] **Step 3: Implement config module**

Create `exchange_cli/core/config.py`:

```python
"""Configuration management — read/write config, encrypt passwords."""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

DEFAULT_CONFIG_DIR = Path.home() / ".exchange-cli"
CONFIG_FILENAME = "config.json"
KEY_FILENAME = ".key"


class ConfigManager:
    def __init__(self, config_dir: Path | None = None):
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
        key = self._get_or_create_key()
        return Fernet(key).encrypt(plaintext.encode()).decode()

    def _decrypt(self, token: str) -> str:
        key = self._get_or_create_key()
        return Fernet(key).decrypt(token.encode()).decode()

    def load_config(self) -> dict | None:
        if not self.config_path.exists():
            return None
        with open(self.config_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_config(self, config: dict):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        self.config_path.chmod(0o600)

    def save_account(
        self, email: str, server: str, username: str, password: str, auth_type: str = "ntlm"
    ):
        config = self.load_config() or {"version": 1, "default_account": email, "accounts": {}}
        config["accounts"][email] = {
            "server": server,
            "username": username,
            "password": self._encrypt(password),
            "auth_type": auth_type,
        }
        if "default_account" not in config or not config["default_account"]:
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
        if not target or target not in config.get("accounts", {}):
            return None

        acc = config["accounts"][target]
        creds = {
            "server": env_server or acc["server"],
            "username": env_username or acc["username"],
            "password": env_password or self._decrypt(acc["password"]),
            "auth_type": env_auth or acc.get("auth_type", "ntlm"),
        }
        return creds

    def get_display_config(self) -> dict | None:
        config = self.load_config()
        if not config:
            return None
        display = json.loads(json.dumps(config))
        for acc in display.get("accounts", {}).values():
            acc["password"] = "********"
        return display
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add exchange_cli/core/config.py tests/test_config.py
git commit -m "feat(core): config module with encrypted password storage"
```

---

### Task 3: Core — Output Module

**Files:**
- Create: `exchange_cli/core/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_output.py`:

```python
import json
import io

import pytest

from exchange_cli.core.output import OutputFormatter


class TestOutputFormatter:
    def test_json_success_single(self):
        f = OutputFormatter("json")
        buf = io.StringIO()
        f.success({"id": "123", "subject": "Hi"}, file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": True, "data": {"id": "123", "subject": "Hi"}}

    def test_json_success_list(self):
        f = OutputFormatter("json")
        buf = io.StringIO()
        items = [{"id": "1"}, {"id": "2"}]
        f.success(items, count=2, file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": True, "count": 2, "data": items}

    def test_json_error(self):
        f = OutputFormatter("json")
        buf = io.StringIO()
        f.error("Connection failed", code="CONNECTION_ERROR", file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": False, "error": "Connection failed", "code": "CONNECTION_ERROR"}

    def test_text_success_single(self):
        f = OutputFormatter("text")
        buf = io.StringIO()
        f.success({"subject": "Hi", "sender": "boss@x.com"}, file=buf)
        output = buf.getvalue()
        assert "subject" in output
        assert "Hi" in output

    def test_text_success_list(self):
        f = OutputFormatter("text")
        buf = io.StringIO()
        items = [{"subject": "A", "sender": "a@x.com"}, {"subject": "B", "sender": "b@x.com"}]
        f.success(items, count=2, file=buf)
        output = buf.getvalue()
        assert "A" in output
        assert "B" in output

    def test_text_error(self):
        f = OutputFormatter("text")
        buf = io.StringIO()
        f.error("Auth failed", code="AUTH_ERROR", file=buf)
        output = buf.getvalue()
        assert "Auth failed" in output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_output.py -v
```

- [ ] **Step 3: Implement output module**

Create `exchange_cli/core/output.py`:

```python
"""Output formatting — JSON (AI-friendly) / Text (human-readable)."""

import json
import sys
from datetime import date, datetime


def _default_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


class OutputFormatter:
    def __init__(self, fmt: str = "json"):
        self.fmt = fmt

    def success(self, data, count: int | None = None, file=None):
        file = file or sys.stdout
        if self.fmt == "json":
            result = {"ok": True, "data": data}
            if count is not None:
                result["count"] = count
            json.dump(result, file, ensure_ascii=False, default=_default_serializer)
            file.write("\n")
        else:
            self._print_text(data, count, file)

    def error(self, message: str, code: str | None = None, file=None):
        file = file or sys.stdout
        if self.fmt == "json":
            result = {"ok": False, "error": message}
            if code:
                result["code"] = code
            json.dump(result, file, ensure_ascii=False)
            file.write("\n")
        else:
            file.write(f"Error [{code}]: {message}\n" if code else f"Error: {message}\n")

    def _print_text(self, data, count, file):
        if isinstance(data, list):
            if not data:
                file.write("(no results)\n")
                return
            keys = list(data[0].keys())
            header = "  ".join(k.ljust(20) for k in keys)
            file.write(header + "\n")
            file.write("-" * len(header) + "\n")
            for row in data:
                line = "  ".join(str(row.get(k, "")).ljust(20) for k in keys)
                file.write(line + "\n")
        elif isinstance(data, dict):
            for k, v in data.items():
                file.write(f"{k}: {v}\n")
        else:
            file.write(str(data) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_output.py -v
```

- [ ] **Step 5: Commit**

```bash
git add exchange_cli/core/output.py tests/test_output.py
git commit -m "feat(core): output formatter with JSON/text modes"
```

---

### Task 4: Core — Connection Module

**Files:**
- Create: `exchange_cli/core/connection.py`
- Create: `tests/test_connection.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_connection.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from exchange_cli.core.connection import ConnectionManager


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
    def test_get_account_creates_connection(self, MockAccount, MockConfig, MockCreds, cm):
        account = cm.get_account()
        MockCreds.assert_called_once_with("DOMAIN\\test", "pass123")
        MockConfig.assert_called_once()
        MockAccount.assert_called_once()
        assert account is MockAccount.return_value

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_get_account_caches(self, MockAccount, MockConfig, MockCreds, cm):
        a1 = cm.get_account()
        a2 = cm.get_account()
        assert a1 is a2
        assert MockAccount.call_count == 1

    def test_get_account_no_config_raises(self, tmp_path):
        from exchange_cli.core.config import ConfigManager
        cfg = ConfigManager(config_dir=tmp_path / ".no-config")
        conn = ConnectionManager(cfg)
        with pytest.raises(SystemExit):
            conn.get_account()

    @patch("exchange_cli.core.connection.Credentials")
    @patch("exchange_cli.core.connection.Configuration")
    @patch("exchange_cli.core.connection.Account")
    def test_env_var_override(self, MockAccount, MockConfig, MockCreds, tmp_path, monkeypatch):
        from exchange_cli.core.config import ConfigManager
        monkeypatch.setenv("EXCHANGE_SERVER", "env.example.com")
        monkeypatch.setenv("EXCHANGE_USERNAME", "envuser")
        monkeypatch.setenv("EXCHANGE_PASSWORD", "envpass")
        cfg = ConfigManager(config_dir=tmp_path / ".exchange-cli")
        conn = ConnectionManager(cfg)
        conn.get_account()
        MockCreds.assert_called_once_with("envuser", "envpass")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_connection.py -v
```

- [ ] **Step 3: Implement connection module**

Create `exchange_cli/core/connection.py`:

```python
"""Connection management — lazy-load exchangelib Account."""

import sys

import click
from exchangelib import Account, Configuration, Credentials, DELEGATE, NTLM
from exchangelib.errors import UnauthorizedError, TransportError

from .config import ConfigManager

ERROR_CODES = {
    "CONFIG_NOT_FOUND": "No configuration found. Run: exchange-cli config init",
    "AUTH_ERROR": "Authentication failed. Check username/password.",
    "CONNECTION_ERROR": "Could not connect to Exchange server.",
}


class ConnectionManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self._accounts: dict[str, Account] = {}

    def get_account(self, email: str | None = None) -> Account:
        cache_key = email or "__default__"
        if cache_key in self._accounts:
            return self._accounts[cache_key]

        creds_dict = self.config_manager.get_account_credentials(email)
        if not creds_dict:
            click.echo(ERROR_CODES["CONFIG_NOT_FOUND"], err=True)
            sys.exit(1)

        try:
            credentials = Credentials(creds_dict["username"], creds_dict["password"])
            server = creds_dict.get("server")

            if server:
                config = Configuration(
                    server=server,
                    credentials=credentials,
                )
                account = Account(
                    primary_smtp_address=email or creds_dict["username"],
                    config=config,
                    autodiscover=False,
                    access_type=DELEGATE,
                )
            else:
                account = Account(
                    primary_smtp_address=email or creds_dict["username"],
                    credentials=credentials,
                    autodiscover=True,
                    access_type=DELEGATE,
                )

            self._accounts[cache_key] = account
            return account
        except UnauthorizedError:
            click.echo(ERROR_CODES["AUTH_ERROR"], err=True)
            sys.exit(1)
        except TransportError as e:
            click.echo(f"{ERROR_CODES['CONNECTION_ERROR']}: {e}", err=True)
            sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_connection.py -v
```

- [ ] **Step 5: Commit**

```bash
git add exchange_cli/core/connection.py tests/test_connection.py
git commit -m "feat(core): connection manager wrapping exchangelib Account"
```

---

### Task 5: Core — Serializers Module

**Files:**
- Create: `exchange_cli/core/serializers.py`
- Create: `tests/test_serializers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_serializers.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, PropertyMock

import pytest

from exchange_cli.core.serializers import (
    serialize_email_summary,
    serialize_email_detail,
    serialize_calendar_event,
    serialize_task,
    serialize_contact,
    serialize_folder,
    serialize_mailbox,
)


def _mock_mailbox(name="Test", email="test@x.com"):
    m = MagicMock()
    m.name = name
    m.email_address = email
    return m


def _mock_message(**kwargs):
    msg = MagicMock()
    msg.id = kwargs.get("id", "AAMk123")
    msg.changekey = kwargs.get("changekey", "CK1")
    msg.subject = kwargs.get("subject", "Test Subject")
    msg.sender = _mock_mailbox("Sender", "sender@x.com")
    msg.to_recipients = [_mock_mailbox("To1", "to1@x.com")]
    msg.cc_recipients = []
    msg.bcc_recipients = []
    msg.datetime_received = kwargs.get("datetime_received", datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc))
    msg.datetime_sent = kwargs.get("datetime_sent", datetime(2024, 7, 15, 10, 29, tzinfo=timezone.utc))
    msg.is_read = kwargs.get("is_read", True)
    msg.has_attachments = kwargs.get("has_attachments", False)
    msg.importance = kwargs.get("importance", "Normal")
    msg.text_body = kwargs.get("text_body", "Preview text")
    msg.body = kwargs.get("body", "<p>Full body</p>")
    msg.attachments = kwargs.get("attachments", [])
    return msg


class TestSerializeMailbox:
    def test_basic(self):
        mb = _mock_mailbox("John", "john@x.com")
        assert serialize_mailbox(mb) == {"name": "John", "email": "john@x.com"}

    def test_none(self):
        assert serialize_mailbox(None) is None


class TestSerializeEmailSummary:
    def test_basic(self):
        msg = _mock_message()
        result = serialize_email_summary(msg)
        assert result["id"] == "AAMk123"
        assert result["subject"] == "Test Subject"
        assert result["sender"]["email"] == "sender@x.com"
        assert result["is_read"] is True
        assert "body" not in result

    def test_with_attachments(self):
        msg = _mock_message(has_attachments=True)
        result = serialize_email_summary(msg)
        assert result["has_attachments"] is True


class TestSerializeEmailDetail:
    def test_includes_body(self):
        msg = _mock_message()
        result = serialize_email_detail(msg)
        assert "body" in result
        assert result["body"] == "<p>Full body</p>"


class TestSerializeCalendarEvent:
    def test_basic(self):
        event = MagicMock()
        event.id = "EVT1"
        event.changekey = "CK1"
        event.subject = "Meeting"
        event.start = datetime(2024, 7, 15, 10, 0, tzinfo=timezone.utc)
        event.end = datetime(2024, 7, 15, 11, 0, tzinfo=timezone.utc)
        event.location = "Room A"
        event.organizer = _mock_mailbox("Boss", "boss@x.com")
        event.required_attendees = [MagicMock(mailbox=_mock_mailbox("John", "john@x.com"), response_type="Accept")]
        event.optional_attendees = []
        event.is_all_day = False
        event.text_body = "Agenda"
        result = serialize_calendar_event(event)
        assert result["subject"] == "Meeting"
        assert result["location"] == "Room A"
        assert len(result["attendees"]) == 1


class TestSerializeTask:
    def test_basic(self):
        task = MagicMock()
        task.id = "T1"
        task.changekey = "CK1"
        task.subject = "Review PR"
        task.status = "NotStarted"
        task.due_date = MagicMock()
        task.due_date.isoformat.return_value = "2024-07-20"
        task.start_date = None
        task.complete_date = None
        task.percent_complete = 0
        task.importance = "Normal"
        task.text_body = "Details"
        result = serialize_task(task)
        assert result["subject"] == "Review PR"
        assert result["status"] == "NotStarted"


class TestSerializeContact:
    def test_basic(self):
        c = MagicMock()
        c.id = "C1"
        c.changekey = "CK1"
        c.display_name = "John Doe"
        c.given_name = "John"
        c.surname = "Doe"
        c.email_addresses = [MagicMock(email="john@x.com", label="EmailAddress1")]
        c.company_name = "Acme"
        c.department = "Engineering"
        c.job_title = "Engineer"
        c.phone_numbers = [MagicMock(phone_number="+1234", label="BusinessPhone")]
        result = serialize_contact(c)
        assert result["display_name"] == "John Doe"
        assert len(result["emails"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_serializers.py -v
```

- [ ] **Step 3: Implement serializers**

Create `exchange_cli/core/serializers.py`:

```python
"""Serialize exchangelib objects to plain dicts for JSON output."""


def _safe_str(val):
    if val is None:
        return None
    return str(val)


def _safe_isoformat(val):
    if val is None:
        return None
    return val.isoformat()


def serialize_mailbox(mb):
    if mb is None:
        return None
    return {"name": mb.name or "", "email": mb.email_address or ""}


def _serialize_mailbox_list(lst):
    if not lst:
        return []
    return [serialize_mailbox(m) for m in lst]


def serialize_attachment_summary(att):
    return {
        "name": getattr(att, "name", None),
        "size": getattr(att, "size", None),
        "content_type": getattr(att, "content_type", None),
    }


def serialize_email_summary(msg):
    return {
        "id": msg.id,
        "subject": msg.subject or "",
        "sender": serialize_mailbox(msg.sender),
        "to": _serialize_mailbox_list(msg.to_recipients),
        "cc": _serialize_mailbox_list(msg.cc_recipients),
        "datetime_received": _safe_isoformat(msg.datetime_received),
        "datetime_sent": _safe_isoformat(msg.datetime_sent),
        "is_read": bool(msg.is_read),
        "has_attachments": bool(msg.has_attachments),
        "importance": _safe_str(msg.importance),
        "body_preview": _safe_str(msg.text_body)[:200] if msg.text_body else "",
    }


def serialize_email_detail(msg):
    result = serialize_email_summary(msg)
    result["body"] = _safe_str(msg.body)
    result["bcc"] = _serialize_mailbox_list(msg.bcc_recipients)
    result["attachments"] = [serialize_attachment_summary(a) for a in (msg.attachments or [])]
    return result


def _serialize_attendee(att):
    return {
        "name": att.mailbox.name if att.mailbox else "",
        "email": att.mailbox.email_address if att.mailbox else "",
        "response": _safe_str(att.response_type),
    }


def serialize_calendar_event(event):
    attendees = []
    for att in (event.required_attendees or []):
        attendees.append(_serialize_attendee(att))
    for att in (event.optional_attendees or []):
        attendees.append(_serialize_attendee(att))

    return {
        "id": event.id,
        "subject": event.subject or "",
        "start": _safe_isoformat(event.start),
        "end": _safe_isoformat(event.end),
        "location": _safe_str(event.location),
        "organizer": serialize_mailbox(event.organizer),
        "attendees": attendees,
        "is_all_day": bool(event.is_all_day),
        "body_preview": _safe_str(event.text_body)[:200] if event.text_body else "",
    }


def serialize_task(task):
    return {
        "id": task.id,
        "subject": task.subject or "",
        "status": _safe_str(task.status),
        "due_date": _safe_isoformat(task.due_date),
        "start_date": _safe_isoformat(task.start_date),
        "complete_date": _safe_isoformat(task.complete_date),
        "percent_complete": task.percent_complete,
        "importance": _safe_str(task.importance),
        "body_preview": _safe_str(task.text_body)[:200] if task.text_body else "",
    }


def serialize_contact(contact):
    emails = []
    for e in (contact.email_addresses or []):
        emails.append({"email": e.email, "label": _safe_str(e.label)})
    phones = []
    for p in (contact.phone_numbers or []):
        phones.append({"number": p.phone_number, "label": _safe_str(p.label)})

    return {
        "id": contact.id,
        "display_name": contact.display_name or "",
        "given_name": contact.given_name or "",
        "surname": contact.surname or "",
        "emails": emails,
        "phones": phones,
        "company": contact.company_name or "",
        "department": contact.department or "",
        "job_title": contact.job_title or "",
    }


def serialize_folder(folder):
    return {
        "id": folder.id if hasattr(folder, "id") else None,
        "name": folder.name or "",
        "total_count": getattr(folder, "total_count", 0),
        "unread_count": getattr(folder, "unread_count", 0),
        "child_folder_count": getattr(folder, "child_folder_count", 0),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_serializers.py -v
```

- [ ] **Step 5: Commit**

```bash
git add exchange_cli/core/serializers.py tests/test_serializers.py
git commit -m "feat(core): serializers for exchangelib objects"
```

---

### Task 6: Command — config {init, show, test}

**Files:**
- Create: `exchange_cli/commands/config.py`
- Modify: `exchange_cli/main.py` (register config group)
- Create: `tests/test_config_cmd.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config_cmd.py`:

```python
import json
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

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
                input="mail.example.com\nDOMAIN\\test\nsecret123\nntlm\ntest@example.com\n",
            )
        assert result.exit_code == 0
        assert "saved" in result.output.lower() or "ok" in result.output.lower()


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_cmd.py -v
```

- [ ] **Step 3: Implement config command group**

Create `exchange_cli/commands/config.py`:

```python
"""exchange-cli config {init, show, test}"""

import sys

import click
from exchangelib import Account, Configuration, Credentials, DELEGATE
from exchangelib.errors import UnauthorizedError, TransportError

from ..core.config import ConfigManager
from ..core.output import OutputFormatter


def _test_connection(server, username, password) -> bool:
    try:
        credentials = Credentials(username, password)
        config = Configuration(server=server, credentials=credentials)
        Account(
            primary_smtp_address=username,
            config=config,
            autodiscover=False,
            access_type=DELEGATE,
        )
        return True
    except Exception:
        return False


@click.group("config")
@click.pass_context
def config(ctx):
    """Manage exchange-cli configuration."""
    pass


@config.command("init")
@click.pass_context
def config_init(ctx):
    """Interactive setup — configure Exchange server credentials."""
    config_path = ctx.obj.get("config_path")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()

    existing = cm.load_config()
    if existing:
        click.echo("Existing configuration found.", err=True)
        if not click.confirm("Add a new account or overwrite?", default=True):
            sys.exit(0)

    server = click.prompt("Exchange Server", type=str)
    username = click.prompt("Username (e.g. DOMAIN\\user or user@domain.com)", type=str)
    password = click.prompt("Password", type=str, hide_input=True)
    auth_type = click.prompt("Auth type", type=click.Choice(["ntlm", "basic"]), default="ntlm")
    email = click.prompt("Email address", type=str)

    click.echo("Testing connection...", err=True)
    if _test_connection(server, username, password):
        click.echo("Connected successfully.", err=True)
    else:
        click.echo("Warning: Connection test failed. Saving config anyway.", err=True)

    cm.save_account(email, server, username, password, auth_type)
    click.echo(f"Configuration saved to {cm.config_path}", err=True)

    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    out.success({"message": "Configuration saved", "account": email})


@config.command("show")
@click.pass_context
def config_show(ctx):
    """Show current configuration (passwords masked)."""
    config_path = ctx.obj.get("config_path")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)

    display = cm.get_display_config()
    if not display:
        out.error("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
        sys.exit(1)
    out.success(display)


@config.command("test")
@click.pass_context
def config_test(ctx):
    """Test connection to Exchange server."""
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)

    creds = cm.get_account_credentials(account_email)
    if not creds:
        out.error("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
        sys.exit(1)

    click.echo("Testing connection...", err=True)
    if _test_connection(creds["server"], creds["username"], creds["password"]):
        out.success({"message": "Connection successful", "server": creds["server"]})
    else:
        out.error("Connection failed", code="CONNECTION_ERROR")
        sys.exit(1)
```

- [ ] **Step 4: Register config group in main.py**

Add to `exchange_cli/main.py`, after the `cli` function definition:

```python
from .commands.config import config
cli.add_command(config)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config_cmd.py -v
```

- [ ] **Step 6: Commit**

```bash
git add exchange_cli/commands/config.py exchange_cli/main.py tests/test_config_cmd.py
git commit -m "feat(cmd): config init/show/test commands"
```

---

### Task 7: Command — email {list, read, send, reply, forward, search}

**Files:**
- Create: `exchange_cli/commands/email.py`
- Modify: `exchange_cli/main.py` (register email group)
- Create: `tests/test_email.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_email.py`:

```python
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


def _mock_message(id="AAMk123", subject="Test", is_read=True):
    msg = MagicMock()
    msg.id = id
    msg.changekey = "CK1"
    msg.subject = subject
    msg.sender = MagicMock(name="Sender", email_address="sender@x.com")
    msg.sender.name = "Sender"
    msg.to_recipients = [MagicMock(name="To", email_address="to@x.com")]
    msg.to_recipients[0].name = "To"
    msg.cc_recipients = []
    msg.bcc_recipients = []
    msg.datetime_received = datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc)
    msg.datetime_sent = datetime(2024, 7, 15, 10, 29, tzinfo=timezone.utc)
    msg.is_read = is_read
    msg.has_attachments = False
    msg.importance = "Normal"
    msg.text_body = "Preview"
    msg.body = "<p>Full body</p>"
    msg.attachments = []
    return msg


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.email.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestEmailList:
    def test_list_inbox(self, runner, mock_conn):
        msgs = [_mock_message("M1", "Subject 1"), _mock_message("M2", "Subject 2")]
        mock_conn.inbox.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=msgs)
        result = runner.invoke(cli, ["email", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["count"] == 2

    def test_list_with_folder(self, runner, mock_conn):
        mock_conn.sent.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "list", "--folder", "sent"])
        assert result.exit_code == 0

    def test_list_unread(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "list", "--unread"])
        assert result.exit_code == 0


class TestEmailRead:
    def test_read_message(self, runner, mock_conn):
        msg = _mock_message()
        mock_conn.inbox.get.return_value = msg
        with patch("exchange_cli.commands.email._find_message", return_value=msg):
            result = runner.invoke(cli, ["email", "read", "AAMk123"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["subject"] == "Test"
        assert "body" in data["data"]


class TestEmailSend:
    def test_send_basic(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["email", "send", "--to", "a@x.com", "--subject", "Hi", "--body", "Hello"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestEmailSearch:
    def test_search_basic(self, runner, mock_conn):
        mock_conn.inbox.filter.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["email", "search", "quarterly report"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_email.py -v
```

- [ ] **Step 3: Implement email command group**

Create `exchange_cli/commands/email.py`:

```python
"""exchange-cli email {list, read, send, reply, forward, search}"""

import os
import sys

import click
from exchangelib import FileAttachment, HTMLBody, Mailbox, Message
from exchangelib.errors import ErrorItemNotFound
from exchangelib.queryset import QuerySet

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_summary, serialize_email_detail


def get_connection(ctx) -> "Account":
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


def _resolve_folder(account, folder_name: str):
    name_upper = folder_name.upper()
    mapping = {
        "INBOX": account.inbox,
        "SENT": account.sent,
        "DRAFTS": account.drafts,
        "TRASH": account.trash,
        "JUNK": account.junk,
    }
    if name_upper in mapping:
        return mapping[name_upper]
    return account.inbox / folder_name


def _find_message(account, message_id: str):
    try:
        return account.inbox.get(id=message_id)
    except ErrorItemNotFound:
        for folder in [account.sent, account.drafts, account.trash, account.junk]:
            try:
                return folder.get(id=message_id)
            except (ErrorItemNotFound, Exception):
                continue
    return None


@click.group("email")
@click.pass_context
def email(ctx):
    """Email operations — list, read, send, reply, forward, search."""
    pass


@email.command("list")
@click.option("--folder", "folder_name", default="inbox", help="Folder name (inbox, sent, drafts, trash, junk)")
@click.option("--limit", default=20, type=int, help="Number of messages to return")
@click.option("--unread", is_flag=True, default=False, help="Only unread messages")
@click.pass_context
def email_list(ctx, folder_name, limit, unread):
    """List messages in a folder (default: inbox, last 20)."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        folder = _resolve_folder(account, folder_name)
        qs = folder.filter(is_read=False) if unread else folder.all()
        items = qs.order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(msg) for msg in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@email.command("read")
@click.argument("message_id")
@click.option("--save-attachments", "save_dir", default=None, help="Directory to save attachments")
@click.pass_context
def email_read(ctx, message_id, save_dir):
    """Read a message by its ID."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg = _find_message(account, message_id)
        if not msg:
            out.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)

        if save_dir:
            os.makedirs(save_dir, exist_ok=True)
            for att in msg.attachments:
                if isinstance(att, FileAttachment):
                    path = os.path.join(save_dir, att.name)
                    with open(path, "wb") as f:
                        f.write(att.content)
                    click.echo(f"Saved: {path}", err=True)

        result = serialize_email_detail(msg)
        out.success(result)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@email.command("send")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--bcc", "bcc_addrs", multiple=True, help="BCC email(s)")
@click.option("--subject", required=True, help="Email subject")
@click.option("--body", default=None, help="Email body text")
@click.option("--body-file", default=None, type=click.Path(exists=True), help="Read body from file")
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.option("--attach", "attachments", multiple=True, type=click.Path(exists=True), help="Attach file(s)")
@click.pass_context
def email_send(ctx, to_addrs, cc_addrs, bcc_addrs, subject, body, body_file, body_type, attachments):
    """Send an email."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)

    if body_file:
        with open(body_file, encoding="utf-8") as f:
            body = f.read()
    if not body:
        out.error("Either --body or --body-file is required", code="INVALID_INPUT")
        sys.exit(1)

    try:
        account = get_connection(ctx)
        msg_body = HTMLBody(body) if body_type == "html" else body
        msg = Message(
            account=account,
            subject=subject,
            body=msg_body,
            to_recipients=[Mailbox(email_address=a) for a in to_addrs],
            cc_recipients=[Mailbox(email_address=a) for a in cc_addrs],
            bcc_recipients=[Mailbox(email_address=a) for a in bcc_addrs],
        )
        for path in attachments:
            with open(path, "rb") as f:
                content = f.read()
            msg.attach(FileAttachment(name=os.path.basename(path), content=content))

        msg.send_and_save()
        out.success({"message": "Email sent", "subject": subject, "to": list(to_addrs)})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@email.command("reply")
@click.argument("message_id")
@click.option("--body", required=True, help="Reply body")
@click.option("--all", "reply_all", is_flag=True, default=False, help="Reply to all")
@click.pass_context
def email_reply(ctx, message_id, body, reply_all):
    """Reply to a message."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg = _find_message(account, message_id)
        if not msg:
            out.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)
        if reply_all:
            msg.reply_all(subject=f"Re: {msg.subject}", body=body)
        else:
            msg.reply(subject=f"Re: {msg.subject}", body=body)
        out.success({"message": "Reply sent", "original_id": message_id})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@email.command("forward")
@click.argument("message_id")
@click.option("--to", "to_addrs", required=True, multiple=True, help="Forward to email(s)")
@click.option("--body", default="", help="Additional message")
@click.pass_context
def email_forward(ctx, message_id, to_addrs, body):
    """Forward a message."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg = _find_message(account, message_id)
        if not msg:
            out.error(f"Message not found: {message_id}", code="NOT_FOUND")
            sys.exit(1)
        msg.forward(
            subject=f"Fwd: {msg.subject}",
            body=body,
            to_recipients=[Mailbox(email_address=a) for a in to_addrs],
        )
        out.success({"message": "Email forwarded", "original_id": message_id, "to": list(to_addrs)})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@email.command("search")
@click.argument("query")
@click.option("--folder", "folder_name", default="inbox", help="Folder to search")
@click.option("--limit", default=20, type=int, help="Max results")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--end", default=None, help="End date (YYYY-MM-DD)")
@click.pass_context
def email_search(ctx, query, folder_name, limit, start, end):
    """Search emails by keyword."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        from datetime import datetime
        from exchangelib import EWSDateTime, EWSTimeZone, Q

        account = get_connection(ctx)
        folder = _resolve_folder(account, folder_name)

        q = Q(subject__icontains=query) | Q(body__icontains=query)
        if start:
            tz = EWSTimeZone.localzone()
            start_dt = tz.localize(EWSDateTime.from_datetime(datetime.strptime(start, "%Y-%m-%d")))
            q &= Q(datetime_received__gte=start_dt)
        if end:
            tz = EWSTimeZone.localzone()
            end_dt = tz.localize(EWSDateTime.from_datetime(datetime.strptime(end, "%Y-%m-%d")))
            q &= Q(datetime_received__lte=end_dt)

        items = folder.filter(q).order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(msg) for msg in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 4: Register email group in main.py**

Add to `exchange_cli/main.py`:

```python
from .commands.email import email
cli.add_command(email)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_email.py -v
```

Adjust mocks as needed to make tests pass. The key pattern: mock `get_connection` to return a mock account.

- [ ] **Step 6: Commit**

```bash
git add exchange_cli/commands/email.py exchange_cli/main.py tests/test_email.py
git commit -m "feat(cmd): email list/read/send/reply/forward/search commands"
```

---

### Task 8: Command — draft {list, create, send, delete}

**Files:**
- Create: `exchange_cli/commands/draft.py`
- Modify: `exchange_cli/main.py` (register draft group)
- Create: `tests/test_draft.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_draft.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.draft.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestDraftList:
    def test_list(self, runner, mock_conn):
        mock_conn.drafts.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["draft", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestDraftCreate:
    def test_create(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["draft", "create", "--to", "a@x.com", "--subject", "Draft", "--body", "WIP"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestDraftSend:
    def test_send(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "send", "D1"])
        assert result.exit_code == 0


class TestDraftDelete:
    def test_delete(self, runner, mock_conn):
        draft = MagicMock()
        draft.id = "D1"
        mock_conn.drafts.get.return_value = draft
        result = runner.invoke(cli, ["draft", "delete", "D1"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Implement draft command group**

Create `exchange_cli/commands/draft.py`:

```python
"""exchange-cli draft {list, create, send, delete}"""

import sys

import click
from exchangelib import HTMLBody, Mailbox, Message
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_email_summary


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


@click.group("draft")
@click.pass_context
def draft(ctx):
    """Draft management — list, create, send, delete."""
    pass


@draft.command("list")
@click.option("--limit", default=20, type=int, help="Number of drafts to return")
@click.pass_context
def draft_list(ctx, limit):
    """List drafts."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        items = account.drafts.all().order_by("-datetime_received")[:limit]
        results = [serialize_email_summary(msg) for msg in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("create")
@click.option("--to", "to_addrs", multiple=True, help="Recipient email(s)")
@click.option("--cc", "cc_addrs", multiple=True, help="CC email(s)")
@click.option("--subject", required=True, help="Subject")
@click.option("--body", required=True, help="Body text")
@click.option("--body-type", default="text", type=click.Choice(["text", "html"]), help="Body type")
@click.pass_context
def draft_create(ctx, to_addrs, cc_addrs, subject, body, body_type):
    """Create a draft."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg_body = HTMLBody(body) if body_type == "html" else body
        msg = Message(
            account=account,
            subject=subject,
            body=msg_body,
            to_recipients=[Mailbox(email_address=a) for a in to_addrs],
            cc_recipients=[Mailbox(email_address=a) for a in cc_addrs],
            folder=account.drafts,
        )
        msg.save()
        out.success({"message": "Draft created", "id": msg.id, "subject": subject})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("send")
@click.argument("draft_id")
@click.pass_context
def draft_send(ctx, draft_id):
    """Send an existing draft."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg = account.drafts.get(id=draft_id)
        msg.send()
        out.success({"message": "Draft sent", "id": draft_id})
    except ErrorItemNotFound:
        out.error(f"Draft not found: {draft_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@draft.command("delete")
@click.argument("draft_id")
@click.pass_context
def draft_delete(ctx, draft_id):
    """Delete a draft."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        msg = account.drafts.get(id=draft_id)
        msg.delete()
        out.success({"message": "Draft deleted", "id": draft_id})
    except ErrorItemNotFound:
        out.error(f"Draft not found: {draft_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 3: Register in main.py**

```python
from .commands.draft import draft
cli.add_command(draft)
```

- [ ] **Step 4: Run tests, commit**

```bash
pytest tests/test_draft.py -v
git add exchange_cli/commands/draft.py exchange_cli/main.py tests/test_draft.py
git commit -m "feat(cmd): draft list/create/send/delete commands"
```

---

### Task 9: Command — folder {list, tree}

**Files:**
- Create: `exchange_cli/commands/folder.py`
- Modify: `exchange_cli/main.py`
- Create: `tests/test_folder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_folder.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.folder.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"

        inbox = MagicMock()
        inbox.id = "F1"
        inbox.name = "Inbox"
        inbox.total_count = 150
        inbox.unread_count = 5
        inbox.child_folder_count = 2

        sent = MagicMock()
        sent.id = "F2"
        sent.name = "Sent Items"
        sent.total_count = 300
        sent.unread_count = 0
        sent.child_folder_count = 0

        account.root.children = [inbox, sent]
        account.msg_folder_root.children = [inbox, sent]
        mock.return_value = account
        yield account


class TestFolderList:
    def test_list(self, runner, mock_conn):
        result = runner.invoke(cli, ["folder", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestFolderTree:
    def test_tree(self, runner, mock_conn):
        result = runner.invoke(cli, ["folder", "tree"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
```

- [ ] **Step 2: Implement folder commands**

Create `exchange_cli/commands/folder.py`:

```python
"""exchange-cli folder {list, tree}"""

import sys

import click

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_folder


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


def _walk_tree(folder, depth=0):
    result = serialize_folder(folder)
    result["depth"] = depth
    items = [result]
    for child in getattr(folder, "children", []):
        items.extend(_walk_tree(child, depth + 1))
    return items


@click.group("folder")
@click.pass_context
def folder(ctx):
    """Folder browsing — list and tree."""
    pass


@folder.command("list")
@click.pass_context
def folder_list(ctx):
    """List top-level folders."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        folders = list(account.msg_folder_root.children)
        results = [serialize_folder(f) for f in folders]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@folder.command("tree")
@click.pass_context
def folder_tree(ctx):
    """Show full folder tree."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        tree = []
        for f in account.msg_folder_root.children:
            tree.extend(_walk_tree(f))
        out.success(tree, count=len(tree))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 3: Register in main.py, run tests, commit**

```python
from .commands.folder import folder
cli.add_command(folder)
```

```bash
pytest tests/test_folder.py -v
git add exchange_cli/commands/folder.py exchange_cli/main.py tests/test_folder.py
git commit -m "feat(cmd): folder list/tree commands"
```

---

### Task 10: Command — calendar {list, create, update, delete}

**Files:**
- Create: `exchange_cli/commands/calendar.py`
- Modify: `exchange_cli/main.py`
- Create: `tests/test_calendar.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_calendar.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.calendar.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestCalendarList:
    def test_list_today(self, runner, mock_conn):
        mock_conn.calendar.view.return_value = []
        result = runner.invoke(cli, ["calendar", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_list_range(self, runner, mock_conn):
        mock_conn.calendar.view.return_value = []
        result = runner.invoke(cli, ["calendar", "list", "--start", "2024-07-01", "--end", "2024-07-31"])
        assert result.exit_code == 0


class TestCalendarCreate:
    def test_create_event(self, runner, mock_conn):
        result = runner.invoke(
            cli,
            ["calendar", "create", "--subject", "Meeting", "--start", "2024-07-15 10:00", "--end", "2024-07-15 11:00"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestCalendarDelete:
    def test_delete_event(self, runner, mock_conn):
        event = MagicMock()
        event.id = "E1"
        mock_conn.calendar.get.return_value = event
        result = runner.invoke(cli, ["calendar", "delete", "E1"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Implement calendar commands**

Create `exchange_cli/commands/calendar.py`:

```python
"""exchange-cli calendar {list, create, update, delete}"""

import sys
from datetime import datetime, timedelta

import click
from exchangelib import CalendarItem, EWSDateTime, EWSTimeZone, Attendee, Mailbox
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_calendar_event


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


def _parse_datetime(dt_str: str) -> EWSDateTime:
    tz = EWSTimeZone.localzone()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return tz.localize(EWSDateTime.from_datetime(dt))
        except ValueError:
            continue
    raise click.BadParameter(f"Invalid datetime: {dt_str}. Use YYYY-MM-DD HH:MM format.")


@click.group("calendar")
@click.pass_context
def calendar(ctx):
    """Calendar events — list, create, update, delete."""
    pass


@calendar.command("list")
@click.option("--start", default=None, help="Start date (YYYY-MM-DD), default: today")
@click.option("--end", default=None, help="End date (YYYY-MM-DD), default: tomorrow")
@click.pass_context
def calendar_list(ctx, start, end):
    """List calendar events."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        tz = EWSTimeZone.localzone()
        now = datetime.now()

        if start:
            start_dt = _parse_datetime(start)
        else:
            start_dt = tz.localize(EWSDateTime(now.year, now.month, now.day))

        if end:
            end_dt = _parse_datetime(end)
        else:
            tomorrow = now + timedelta(days=1)
            end_dt = tz.localize(EWSDateTime(tomorrow.year, tomorrow.month, tomorrow.day))

        events = list(account.calendar.view(start=start_dt, end=end_dt))
        results = [serialize_calendar_event(e) for e in events]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@calendar.command("create")
@click.option("--subject", required=True, help="Event subject")
@click.option("--start", required=True, help="Start datetime (YYYY-MM-DD HH:MM)")
@click.option("--end", required=True, help="End datetime (YYYY-MM-DD HH:MM)")
@click.option("--location", default=None, help="Location")
@click.option("--body", default="", help="Event body/description")
@click.option("--attendees", default=None, help="Comma-separated attendee emails")
@click.pass_context
def calendar_create(ctx, subject, start, end, location, body, attendees):
    """Create a calendar event."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        event = CalendarItem(
            account=account,
            folder=account.calendar,
            subject=subject,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
            location=location,
            body=body,
        )
        if attendees:
            event.required_attendees = [
                Attendee(mailbox=Mailbox(email_address=a.strip()))
                for a in attendees.split(",")
            ]
        event.save(send_meeting_invitations="SendToAllAndSaveCopy" if attendees else "SendToNone")
        out.success({"message": "Event created", "id": event.id, "subject": subject})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@calendar.command("update")
@click.argument("event_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--start", default=None, help="New start datetime")
@click.option("--end", default=None, help="New end datetime")
@click.option("--location", default=None, help="New location")
@click.pass_context
def calendar_update(ctx, event_id, subject, start, end, location):
    """Update a calendar event."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        if subject:
            event.subject = subject
        if start:
            event.start = _parse_datetime(start)
        if end:
            event.end = _parse_datetime(end)
        if location:
            event.location = location
        event.save(update_fields=["subject", "start", "end", "location"])
        out.success({"message": "Event updated", "id": event_id})
    except ErrorItemNotFound:
        out.error(f"Event not found: {event_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@calendar.command("delete")
@click.argument("event_id")
@click.pass_context
def calendar_delete(ctx, event_id):
    """Delete a calendar event."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        event = account.calendar.get(id=event_id)
        event.delete()
        out.success({"message": "Event deleted", "id": event_id})
    except ErrorItemNotFound:
        out.error(f"Event not found: {event_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 3: Register in main.py, run tests, commit**

```python
from .commands.calendar import calendar
cli.add_command(calendar)
```

```bash
pytest tests/test_calendar.py -v
git add exchange_cli/commands/calendar.py exchange_cli/main.py tests/test_calendar.py
git commit -m "feat(cmd): calendar list/create/update/delete commands"
```

---

### Task 11: Command — task {list, create, update, complete, delete}

**Files:**
- Create: `exchange_cli/commands/task.py`
- Modify: `exchange_cli/main.py`
- Create: `tests/test_task.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_task.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.task.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestTaskList:
    def test_list(self, runner, mock_conn):
        mock_conn.tasks.all.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["task", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestTaskCreate:
    def test_create(self, runner, mock_conn):
        result = runner.invoke(cli, ["task", "create", "--subject", "Review PR"])
        assert result.exit_code == 0


class TestTaskComplete:
    def test_complete(self, runner, mock_conn):
        t = MagicMock()
        t.id = "T1"
        mock_conn.tasks.get.return_value = t
        result = runner.invoke(cli, ["task", "complete", "T1"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Implement task commands**

Create `exchange_cli/commands/task.py`:

```python
"""exchange-cli task {list, create, update, complete, delete}"""

import sys
from datetime import datetime
from decimal import Decimal

import click
from exchangelib import EWSDate, Task as EWSTask
from exchangelib.errors import ErrorItemNotFound

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_task


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


@click.group("task")
@click.pass_context
def task(ctx):
    """Task management — list, create, update, complete, delete."""
    pass


@task.command("list")
@click.option("--limit", default=50, type=int, help="Max results")
@click.option("--status", default=None, help="Filter by status (NotStarted, InProgress, Completed, WaitingOnOthers, Deferred)")
@click.pass_context
def task_list(ctx, limit, status):
    """List tasks."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        qs = account.tasks.filter(status=status) if status else account.tasks.all()
        items = qs.order_by("-due_date")[:limit]
        results = [serialize_task(t) for t in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@task.command("create")
@click.option("--subject", required=True, help="Task subject")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.option("--body", default="", help="Task body/description")
@click.option("--status", default="NotStarted", help="Initial status")
@click.pass_context
def task_create(ctx, subject, due, body, status):
    """Create a task."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        t = EWSTask(
            account=account,
            folder=account.tasks,
            subject=subject,
            body=body,
            status=status,
        )
        if due:
            t.due_date = EWSDate.from_date(datetime.strptime(due, "%Y-%m-%d").date())
        t.save()
        out.success({"message": "Task created", "id": t.id, "subject": subject})
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@task.command("update")
@click.argument("task_id")
@click.option("--subject", default=None, help="New subject")
@click.option("--due", default=None, help="New due date (YYYY-MM-DD)")
@click.option("--status", default=None, help="New status")
@click.pass_context
def task_update(ctx, task_id, subject, due, status):
    """Update a task."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        t = account.tasks.get(id=task_id)
        fields = []
        if subject:
            t.subject = subject
            fields.append("subject")
        if due:
            t.due_date = EWSDate.from_date(datetime.strptime(due, "%Y-%m-%d").date())
            fields.append("due_date")
        if status:
            t.status = status
            fields.append("status")
        if fields:
            t.save(update_fields=fields)
        out.success({"message": "Task updated", "id": task_id})
    except ErrorItemNotFound:
        out.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@task.command("complete")
@click.argument("task_id")
@click.pass_context
def task_complete(ctx, task_id):
    """Mark a task as completed."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        t = account.tasks.get(id=task_id)
        t.status = "Completed"
        t.percent_complete = Decimal(100)
        t.save(update_fields=["status", "percent_complete"])
        out.success({"message": "Task completed", "id": task_id})
    except ErrorItemNotFound:
        out.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@task.command("delete")
@click.argument("task_id")
@click.pass_context
def task_delete(ctx, task_id):
    """Delete a task."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        t = account.tasks.get(id=task_id)
        t.delete()
        out.success({"message": "Task deleted", "id": task_id})
    except ErrorItemNotFound:
        out.error(f"Task not found: {task_id}", code="NOT_FOUND")
        sys.exit(1)
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 3: Register in main.py, run tests, commit**

```python
from .commands.task import task
cli.add_command(task)
```

```bash
pytest tests/test_task.py -v
git add exchange_cli/commands/task.py exchange_cli/main.py tests/test_task.py
git commit -m "feat(cmd): task list/create/update/complete/delete commands"
```

---

### Task 12: Command — contact {list, search}

**Files:**
- Create: `exchange_cli/commands/contact.py`
- Modify: `exchange_cli/main.py`
- Create: `tests/test_contact.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_contact.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from exchange_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_conn():
    with patch("exchange_cli.commands.contact.get_connection") as mock:
        account = MagicMock()
        account.primary_smtp_address = "test@example.com"
        mock.return_value = account
        yield account


class TestContactList:
    def test_list(self, runner, mock_conn):
        mock_conn.contacts.all.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["contact", "list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestContactSearch:
    def test_search(self, runner, mock_conn):
        mock_conn.contacts.filter.return_value.__getitem__ = MagicMock(return_value=[])
        result = runner.invoke(cli, ["contact", "search", "John"])
        assert result.exit_code == 0
```

- [ ] **Step 2: Implement contact commands**

Create `exchange_cli/commands/contact.py`:

```python
"""exchange-cli contact {list, search}"""

import sys

import click
from exchangelib import Q

from ..core.config import ConfigManager
from ..core.connection import ConnectionManager
from ..core.output import OutputFormatter
from ..core.serializers import serialize_contact


def get_connection(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    cm = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    conn = ConnectionManager(cm)
    return conn.get_account(account_email)


@click.group("contact")
@click.pass_context
def contact(ctx):
    """Contacts — list and search."""
    pass


@contact.command("list")
@click.option("--limit", default=50, type=int, help="Max contacts to return")
@click.pass_context
def contact_list(ctx, limit):
    """List contacts."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        items = account.contacts.all()[:limit]
        results = [serialize_contact(c) for c in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)


@contact.command("search")
@click.argument("query")
@click.option("--limit", default=20, type=int, help="Max results")
@click.pass_context
def contact_search(ctx, query, limit):
    """Search contacts by name or email."""
    fmt = ctx.obj.get("fmt", "json")
    out = OutputFormatter(fmt)
    try:
        account = get_connection(ctx)
        q = Q(display_name__icontains=query) | Q(email_addresses__icontains=query)
        items = account.contacts.filter(q)[:limit]
        results = [serialize_contact(c) for c in items]
        out.success(results, count=len(results))
    except Exception as e:
        out.error(str(e), code="SERVER_ERROR")
        sys.exit(1)
```

- [ ] **Step 3: Register in main.py, run tests, commit**

```python
from .commands.contact import contact
cli.add_command(contact)
```

```bash
pytest tests/test_contact.py -v
git add exchange_cli/commands/contact.py exchange_cli/main.py tests/test_contact.py
git commit -m "feat(cmd): contact list/search commands"
```

---

### Task 13: Droid Skill File

**Files:**
- Create: `skills/SKILL.md`

- [ ] **Step 1: Create skill file**

Create `skills/SKILL.md`:

```markdown
---
name: exchange-cli
version: 1.0.0
description: |
  Exchange邮件CLI工具：收发邮件、搜索邮件、管理草稿、查看日历事件、管理任务、查询联系人。
  当用户需要收发Exchange/Outlook邮件、查看日历、管理任务、搜索联系人时使用。
  即使用户只是说"帮我查一下邮件"、"发一封邮件给xxx"、"看看今天有什么会议"，也应该触发。
metadata:
  requires:
    bins: ["exchange-cli"]
  cliHelp: "exchange-cli --help"
---

# exchange-cli 命令参考

exchange-cli 是一个 Exchange Web Services CLI 工具，直接连接 Exchange/Office 365 服务器。

## 安全与执行规则

- 发送邮件前必须向用户确认收件人、主题和正文
- 删除操作（邮件、日历事件、任务）前必须确认
- 不要在输出中暴露密码或配置文件中的敏感信息
- config init 涉及密码输入，需要用户交互

## 初始化

首次使用前运行 `exchange-cli config init` 交互式配置。

也可通过环境变量配置（适合 CI/非交互场景）：
- `EXCHANGE_SERVER` — Exchange 服务器地址
- `EXCHANGE_USERNAME` — 用户名
- `EXCHANGE_PASSWORD` — 密码
- `EXCHANGE_AUTH_TYPE` — 认证类型 (ntlm/basic)

## 全局参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--format json\|text` | `json` | 输出格式 |
| `--config <path>` | `~/.exchange-cli/config.json` | 配置文件路径 |
| `--account <email>` | default_account | 指定账户 |
| `--verbose` | false | 调试模式 |

## 命令速查表

| 命令 | 用途 | 典型场景 |
|------|------|---------|
| `config init` | 交互式配置 | 首次使用 |
| `config show` | 显示配置 | 检查当前配置 |
| `config test` | 测试连接 | 验证配置是否正确 |
| `email list` | 收件箱列表 | 查看最近邮件 |
| `email read <id>` | 读取邮件 | 查看邮件正文 |
| `email send` | 发送邮件 | 发邮件给某人 |
| `email reply <id>` | 回复邮件 | 回复某封邮件 |
| `email forward <id>` | 转发邮件 | 转发给其他人 |
| `email search <query>` | 搜索邮件 | 搜索特定邮件 |
| `draft list` | 草稿列表 | 查看草稿箱 |
| `draft create` | 创建草稿 | 先存草稿 |
| `draft send <id>` | 发送草稿 | 发送已有草稿 |
| `draft delete <id>` | 删除草稿 | 删除不需要的草稿 |
| `folder list` | 文件夹列表 | 查看文件夹 |
| `folder tree` | 文件夹树 | 查看完整目录结构 |
| `calendar list` | 日历事件 | 查看今天的会议 |
| `calendar create` | 创建事件 | 安排新会议 |
| `calendar update <id>` | 更新事件 | 修改会议信息 |
| `calendar delete <id>` | 删除事件 | 取消会议 |
| `task list` | 任务列表 | 查看待办 |
| `task create` | 创建任务 | 新增待办 |
| `task complete <id>` | 完成任务 | 标记完成 |
| `task delete <id>` | 删除任务 | 删除待办 |
| `contact list` | 联系人列表 | 查看联系人 |
| `contact search <query>` | 搜索联系人 | 查找某人 |

## 详细命令参考

### email list

```bash
exchange-cli email list                           # 收件箱最近 20 封
exchange-cli email list --folder sent --limit 50  # 已发送 50 封
exchange-cli email list --unread                  # 仅未读
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--folder` | `inbox` | 文件夹 (inbox/sent/drafts/trash/junk) |
| `--limit` | `20` | 返回数量 |
| `--unread` | false | 仅未读 |

### email read

```bash
exchange-cli email read MESSAGE_ID
exchange-cli email read MESSAGE_ID --save-attachments ./downloads
```

### email send

```bash
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
exchange-cli email send --to "a@x.com" --cc "b@x.com" --subject "Hi" --body-file ./content.html --body-type html
exchange-cli email send --to "a@x.com" --subject "Report" --attach report.pdf --body "See attached"
```

### email search

```bash
exchange-cli email search "quarterly report"
exchange-cli email search "keyword" --folder sent --start "2024-01-01" --end "2024-06-30"
```

### calendar list

```bash
exchange-cli calendar list                        # 今日事件
exchange-cli calendar list --start "2024-07-01" --end "2024-07-31"
```

### calendar create

```bash
exchange-cli calendar create --subject "Meeting" --start "2024-07-15 10:00" --end "2024-07-15 11:00"
exchange-cli calendar create --subject "Sync" --start "2024-07-15 14:00" --end "2024-07-15 14:30" --attendees "a@x.com,b@x.com" --location "Room A"
```

### task create

```bash
exchange-cli task create --subject "Review PR" --due "2024-07-20"
exchange-cli task list --status NotStarted
```

## JSON 输出格式

成功：`{"ok": true, "data": ..., "count": N}`
错误：`{"ok": false, "error": "...", "code": "ERROR_CODE"}`

错误码：CONFIG_NOT_FOUND, AUTH_ERROR, CONNECTION_ERROR, TIMEOUT_ERROR, NOT_FOUND, INVALID_INPUT, PERMISSION_ERROR, SERVER_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add skills/SKILL.md
git commit -m "docs: add Droid skill file for AI agents"
```

---

### Task 14: npm Distribution Package

**Files:**
- Create: `npm/exchange-cli/package.json`
- Create: `npm/exchange-cli/install.js`
- Create: `npm/exchange-cli/bin/exchange-cli.js`
- Create: `npm/platforms/darwin-arm64/package.json`

- [ ] **Step 1: Create npm wrapper package**

Create `npm/exchange-cli/package.json`:

```json
{
  "name": "@canghe_ai/exchange-cli",
  "version": "0.1.0",
  "description": "Exchange Web Services CLI — email, calendar, tasks, contacts. Designed for AI agents.",
  "bin": {
    "exchange-cli": "bin/exchange-cli.js"
  },
  "scripts": {
    "postinstall": "node install.js"
  },
  "files": [
    "bin/",
    "install.js"
  ],
  "optionalDependencies": {
    "@canghe_ai/exchange-cli-darwin-arm64": "0.1.0"
  },
  "engines": {
    "node": ">=14"
  },
  "keywords": ["exchange", "ews", "cli", "email", "ai-agent", "office365"],
  "license": "Apache-2.0",
  "repository": {
    "type": "git",
    "url": "https://github.com/canghe/exchange-cli"
  },
  "publishConfig": {
    "access": "public"
  }
}
```

- [ ] **Step 2: Create install.js**

Create `npm/exchange-cli/install.js`:

```javascript
#!/usr/bin/env node
'use strict';

const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@canghe_ai/exchange-cli-darwin-arm64',
};

const platformKey = `${process.platform}-${process.arch}`;
const pkg = PLATFORM_PACKAGES[platformKey];

if (!pkg) {
  console.log(`exchange-cli: no binary for ${platformKey}, skipping`);
  process.exit(0);
}

const ext = process.platform === 'win32' ? '.exe' : '';

try {
  const binaryPath = require.resolve(`${pkg}/bin/exchange-cli${ext}`);
  if (process.platform !== 'win32') {
    fs.chmodSync(binaryPath, 0o755);
    console.log(`exchange-cli: set executable permission for ${platformKey}`);
  }
} catch {
  console.log(`exchange-cli: platform package ${pkg} not installed`);
  console.log('To fix: npm install --force @canghe_ai/exchange-cli');
}
```

- [ ] **Step 3: Create bin/exchange-cli.js**

Create `npm/exchange-cli/bin/exchange-cli.js`:

```javascript
#!/usr/bin/env node

const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const PLATFORM_PACKAGES = {
  'darwin-arm64': '@canghe_ai/exchange-cli-darwin-arm64',
};

const platformKey = `${process.platform}-${process.arch}`;
const ext = process.platform === 'win32' ? '.exe' : '';

function getBinaryPath() {
  if (process.env.EXCHANGE_CLI_BINARY) {
    return process.env.EXCHANGE_CLI_BINARY;
  }

  const pkg = PLATFORM_PACKAGES[platformKey];
  if (!pkg) {
    console.error(`exchange-cli: unsupported platform ${platformKey}`);
    process.exit(1);
  }

  try {
    return require.resolve(`${pkg}/bin/exchange-cli${ext}`);
  } catch {
    const modPath = path.join(
      path.dirname(require.resolve(`${pkg}/package.json`)),
      `bin/exchange-cli${ext}`
    );
    if (fs.existsSync(modPath)) return modPath;
  }

  console.error(`exchange-cli: binary not found for ${platformKey}`);
  console.error('Try: npm install --force @canghe_ai/exchange-cli');
  process.exit(1);
}

try {
  execFileSync(getBinaryPath(), process.argv.slice(2), {
    stdio: 'inherit',
    env: { ...process.env },
  });
} catch (e) {
  if (e && e.status != null) process.exit(e.status);
  throw e;
}
```

- [ ] **Step 4: Create platform package**

Create `npm/platforms/darwin-arm64/package.json`:

```json
{
  "name": "@canghe_ai/exchange-cli-darwin-arm64",
  "version": "0.1.0",
  "description": "exchange-cli binary for macOS arm64",
  "os": ["darwin"],
  "cpu": ["arm64"],
  "files": ["bin/"],
  "license": "Apache-2.0",
  "publishConfig": {
    "access": "public"
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add npm/
git commit -m "feat: npm distribution package (macOS arm64)"
```

---

### Task 15: CI/CD Workflows

**Files:**
- Create: `.github/workflows/test.yml`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create test workflow**

Create `.github/workflows/test.yml`:

```yaml
name: Test

on:
  pull_request:
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check exchange_cli/ tests/
      - run: pytest tests/ -v
```

- [ ] **Step 2: Create release workflow**

Create `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  publish-pypi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build twine
      - run: python -m build
      - run: twine upload dist/*
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}

  publish-npm:
    runs-on: ubuntu-latest
    needs: publish-pypi
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"
      - run: cd npm/exchange-cli && npm publish --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

- [ ] **Step 3: Commit**

```bash
git add .github/
git commit -m "ci: add test and release workflows"
```

---

### Task 16: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

Create `README.md` with:
- Project name and description badge
- Quick start example (3 commands: install, init, list)
- Feature list
- Installation section (pip and npm)
- Command reference table (same as spec)
- AI agent usage section (JSON output format, environment variable config)
- License

Follow the structure of `wechat-cli/README.md` but adapted for Exchange.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with usage guide and command reference"
```

---

### Task 17: Final Integration Test & Lint

**Files:**
- All files

- [ ] **Step 1: Run full lint**

```bash
ruff check exchange_cli/ tests/
```

Fix any issues found.

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Fix any failing tests.

- [ ] **Step 3: Verify CLI entry point**

```bash
pip install -e ".[dev]"
exchange-cli --version
exchange-cli --help
exchange-cli email --help
exchange-cli calendar --help
exchange-cli task --help
exchange-cli contact --help
exchange-cli config --help
exchange-cli draft --help
exchange-cli folder --help
```

All should produce help text with no errors.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final lint fixes and integration verification"
```
