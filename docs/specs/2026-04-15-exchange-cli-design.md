# exchange-cli Design Spec

> Date: 2026-04-15
> Status: Approved

## Overview

Transform the exchangelib project into **exchange-cli** — a lightweight, AI-agent-friendly command-line tool for Microsoft Exchange Web Services. Directly wraps exchangelib with no database, Docker, or web server dependencies. Install via `pip` or `npm`.

## Goals

- **AI-first**: JSON output by default, structured error codes, predictable command patterns
- **Zero infrastructure**: `pip install exchange-cli` and ready to use
- **Complete Exchange coverage**: email, drafts, folders, calendar, tasks, contacts
- **Open-source ready**: Apache-2.0 license, CI/CD, PyPI + npm dual publishing

## Architecture: Nested Command Groups (git/gh style)

Commands follow the `exchange-cli <resource> <action>` pattern (e.g. `exchange-cli email list`). This mirrors `gh repo list`, `kubectl get pods`, `aws s3 ls` — well-understood by both humans and AI agents.

## Project Structure

```
exchange-cli/
├── exchange_cli/
│   ├── __init__.py          # __version__
│   ├── main.py              # Click group entry, register all command groups
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── config.py        # exchange-cli config {init,show,test}
│   │   ├── email.py         # exchange-cli email {list,read,send,reply,forward,search}
│   │   ├── draft.py         # exchange-cli draft {list,create,send,delete}
│   │   ├── folder.py        # exchange-cli folder {list,tree}
│   │   ├── calendar.py      # exchange-cli calendar {list,create,update,delete}
│   │   ├── task.py          # exchange-cli task {list,create,update,complete,delete}
│   │   └── contact.py       # exchange-cli contact {list,search}
│   ├── core/
│   │   ├── __init__.py
│   │   ├── connection.py    # exchangelib Account connection (lazy singleton)
│   │   ├── config.py        # Config file read/write (~/.exchange-cli/config.json)
│   │   └── output.py        # JSON/text output formatting
│   └── bin/                 # Pre-built binaries for npm distribution
├── npm/
│   ├── package.json
│   └── index.js             # JS wrapper that spawns Python process
├── skills/
│   └── exchange-cli.md      # Droid skill file for AI agents
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_email.py
│   ├── test_draft.py
│   ├── test_calendar.py
│   ├── test_task.py
│   ├── test_contact.py
│   ├── test_folder.py
│   └── test_output.py
├── pyproject.toml
├── README.md
├── LICENSE
└── .github/
    └── workflows/
        ├── test.yml         # PR: lint + test
        └── release.yml      # Tag: PyPI + npm publish
```

## Command System

### Global Options

```
--format json|text    # Output format, default: json
--config PATH         # Config file path, default: ~/.exchange-cli/config.json
--account EMAIL       # Specify account (overrides default_account in config)
--verbose             # Debug mode, print EWS details to stderr
```

### Command Reference

| Group | Subcommands | Description |
|-------|-------------|-------------|
| `config` | `init`, `show`, `test` | Configuration management |
| `email` | `list`, `read`, `send`, `reply`, `forward`, `search` | Email operations |
| `draft` | `list`, `create`, `send`, `delete` | Draft management |
| `folder` | `list`, `tree` | Folder browsing |
| `calendar` | `list`, `create`, `update`, `delete` | Calendar events |
| `task` | `list`, `create`, `update`, `complete`, `delete` | Task management |
| `contact` | `list`, `search` | Contacts |

### Key Command Parameters

```bash
# Config
exchange-cli config init                          # Interactive setup
exchange-cli config show                          # Show config (password masked)
exchange-cli config test                          # Test connection

# Email
exchange-cli email list                           # Inbox, last 20
exchange-cli email list --folder sent --limit 50
exchange-cli email list --unread
exchange-cli email read MESSAGE_ID
exchange-cli email read MESSAGE_ID --save-attachments ./downloads
exchange-cli email send --to "a@x.com" --subject "Hi" --body "Hello"
exchange-cli email send --to "a@x.com" --subject "Hi" --body-file ./content.html --body-type html
exchange-cli email send --to "a@x.com" --subject "Report" --body "See attached" --attach report.pdf
exchange-cli email reply MESSAGE_ID --body "Thanks"
exchange-cli email reply MESSAGE_ID --all --body "Thanks everyone"
exchange-cli email forward MESSAGE_ID --to "b@x.com" --body "FYI"
exchange-cli email search "quarterly report" --folder inbox --limit 20
exchange-cli email search "from:boss@x.com" --start "2024-01-01" --end "2024-06-30"

# Draft
exchange-cli draft list
exchange-cli draft create --to "a@x.com" --subject "Draft" --body "WIP"
exchange-cli draft send DRAFT_ID
exchange-cli draft delete DRAFT_ID

# Folder
exchange-cli folder list
exchange-cli folder tree

# Calendar
exchange-cli calendar list                        # Today's events
exchange-cli calendar list --start "2024-07-01" --end "2024-07-31"
exchange-cli calendar create --subject "Meeting" --start "2024-07-15 10:00" --end "2024-07-15 11:00" --location "Room A"
exchange-cli calendar create --subject "Sync" --start "2024-07-15 14:00" --end "2024-07-15 14:30" --attendees "a@x.com,b@x.com"
exchange-cli calendar update EVENT_ID --subject "Updated Meeting"
exchange-cli calendar delete EVENT_ID

# Task
exchange-cli task list
exchange-cli task list --status not_started
exchange-cli task create --subject "Review PR" --due "2024-07-20"
exchange-cli task update TASK_ID --subject "Updated task"
exchange-cli task complete TASK_ID
exchange-cli task delete TASK_ID

# Contact
exchange-cli contact list --limit 50
exchange-cli contact search "John"
```

## Configuration & Connection

### Config File: `~/.exchange-cli/config.json`

```json
{
  "version": 1,
  "default_account": "john@example.com",
  "accounts": {
    "john@example.com": {
      "server": "mail.example.com",
      "username": "DOMAIN\\john",
      "password": "<encrypted>",
      "auth_type": "ntlm"
    }
  }
}
```

### Multi-account Support

- `accounts` is a map keyed by email address
- `default_account` specifies which to use by default
- `--account` flag overrides at runtime

### Password Encryption

- Fernet symmetric encryption (from `cryptography` library)
- Key stored at `~/.exchange-cli/.key` with `600` permissions
- Key auto-generated on first `config init`

### Environment Variable Fallback

| Variable | Maps to |
|----------|---------|
| `EXCHANGE_SERVER` | server |
| `EXCHANGE_USERNAME` | username |
| `EXCHANGE_PASSWORD` | password (plaintext) |
| `EXCHANGE_AUTH_TYPE` | auth_type (default: ntlm) |

Environment variables take **higher priority** than config file. Useful for CI/Docker.

### `config init` Flow

1. Prompt for server, username, password, auth_type
2. Auto-run connection test
3. On success, save encrypted config
4. If config exists, prompt to overwrite or add new account

### Connection Management

```python
class ConnectionManager:
    """Lazy-load exchangelib Account, lifecycle = CLI process."""
    
    def get_account(self, email: str | None = None) -> Account:
        # 1. Env vars > config file
        # 2. Build Credentials + Configuration
        # 3. Create Account (autodiscover=True if no server)
        # 4. Cache in self._accounts dict
```

- **No connection pooling** — CLI is short-lived, one connection per invocation
- **Autodiscover** — if server not specified, use exchangelib autodiscover
- **Timeouts** — connection: 30s, operation: 60s
- **Error mapping** — exchangelib exceptions mapped to CLI error codes

## Output Format

### JSON Output (default)

All commands produce a consistent JSON envelope on **stdout**:

```json
// Success - list
{"ok": true, "count": 2, "data": [...]}

// Success - single item
{"ok": true, "data": {...}}

// Error
{"ok": false, "error": "Connection failed", "code": "CONNECTION_ERROR"}
```

Errors also print human-readable messages to **stderr**.

### Data Serialization

Email:
```json
{
    "id": "AAMkAD...",
    "subject": "Quarterly Report",
    "sender": {"name": "Boss", "email": "boss@x.com"},
    "to": [{"name": "John", "email": "john@x.com"}],
    "cc": [],
    "datetime_received": "2024-07-15T10:30:00+08:00",
    "datetime_sent": "2024-07-15T10:29:55+08:00",
    "is_read": true,
    "has_attachments": true,
    "importance": "normal",
    "body_preview": "Please find the quarterly...",
    "body": "<html>...</html>",
    "attachments": [
        {"name": "report.pdf", "size": 102400, "content_type": "application/pdf"}
    ]
}
```

Calendar event:
```json
{
    "id": "AAMkAD...",
    "subject": "Weekly Sync",
    "start": "2024-07-15T10:00:00+08:00",
    "end": "2024-07-15T11:00:00+08:00",
    "location": "Room A",
    "organizer": {"name": "Boss", "email": "boss@x.com"},
    "attendees": [
        {"name": "John", "email": "john@x.com", "response": "accepted"}
    ],
    "is_all_day": false,
    "body_preview": "Agenda: ..."
}
```

### Error Codes

| Code | Meaning | Trigger |
|------|---------|---------|
| `CONFIG_NOT_FOUND` | No config found | No init and no env vars |
| `AUTH_ERROR` | Authentication failed | Wrong credentials |
| `CONNECTION_ERROR` | Connection failed | Server unreachable |
| `TIMEOUT_ERROR` | Operation timeout | EWS request timeout |
| `NOT_FOUND` | Resource not found | Invalid message/event ID |
| `INVALID_INPUT` | Bad parameters | Missing required param, bad format |
| `PERMISSION_ERROR` | Access denied | No permission to folder/mailbox |
| `SERVER_ERROR` | Server error | Exchange server internal error |

### Text Format

List output as table, single items as key-value:

```
$ exchange-cli email list --format text
# Subject                    From              Date                 Read
1 Quarterly Report           boss@x.com        2024-07-15 10:30     ✓
2 Meeting Tomorrow           alice@x.com       2024-07-15 09:15     ✗

$ exchange-cli email read AAMkAD... --format text
Subject:  Quarterly Report
From:     Boss <boss@x.com>
To:       John <john@x.com>
Date:     2024-07-15 10:30
---
Please find the quarterly report attached...
```

## Distribution

### PyPI

- Package name: `exchange-cli`
- Entry point: `exchange-cli = "exchange_cli.main:cli"`
- Python >= 3.10
- Core deps: `click>=8.1`, `exchangelib>=5.0`, `cryptography>=41.0`

### npm

- Package name: `@canghe_ai/exchange-cli`
- JS wrapper spawns Python binary or falls back to pip
- First version: macOS arm64 only

### pyproject.toml

```toml
[project]
name = "exchange-cli"
description = "CLI for Microsoft Exchange Web Services — designed for AI agents"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1,<9",
    "exchangelib>=5.0",
    "cryptography>=41.0",
]
license = "Apache-2.0"
keywords = ["exchange", "ews", "cli", "email", "ai-agent", "office365"]

[project.scripts]
exchange-cli = "exchange_cli.main:cli"
```

## Testing

- **Framework**: pytest + click.testing.CliRunner
- **Mock**: All tests mock exchangelib network layer, no real Exchange server needed
- **Coverage**: Each subcommand's happy path + error path + param validation
- **CI**: GitHub Actions runs `ruff check` + `pytest` on every PR

## CI/CD

- `test.yml`: Triggered on PR — ruff lint + pytest
- `release.yml`: Triggered on `v*` tag push — lint -> test -> build PyPI wheel -> build npm package -> publish both

## Auth Scope (v1)

- Username + password only (NTLM/Basic)
- OAuth2/MSAL deferred to v2

## Non-Goals (v1)

- No webhook/streaming support (unlike exchange-gateway)
- No email templates with variable substitution
- No database or persistent state beyond config file
- No admin dashboard or web UI
