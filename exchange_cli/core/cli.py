"""Shared CLI helpers for command modules."""

from __future__ import annotations

from .config import ConfigManager
from .connection import ConnectionManager


def get_account(ctx):
    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    return ConnectionManager(config_manager).get_account(account_email)
