"""exchange-cli daemon {start,status,stop}."""

import sys

import click

from ..core.daemon import build_daemon_state, daemon_ping, start_daemon, stop_daemon
from ..core.output import OutputFormatter


@click.group("daemon")
@click.pass_context
def daemon(ctx):
    """Manage local background daemon."""


@daemon.command("start")
@click.option("--wait-seconds", default=5.0, type=float, show_default=True, help="Wait timeout for daemon startup")
@click.pass_context
def daemon_start(ctx, wait_seconds):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    state = build_daemon_state(ctx.obj.get("config_path"))
    try:
        started = start_daemon(state, timeout_seconds=wait_seconds)
    except Exception as exc:
        formatter.error(str(exc), code="DAEMON_START_FAILED")
        sys.exit(1)
    ping = daemon_ping(state)
    payload = {
        "status": "running",
        "pid": ping.get("pid") if ping else None,
        "socket": str(state.socket_path),
        "started": bool(started),
    }
    formatter.success(payload)


@daemon.command("status")
@click.pass_context
def daemon_status(ctx):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    state = build_daemon_state(ctx.obj.get("config_path"))
    ping = daemon_ping(state)
    if not ping:
        formatter.success({"status": "stopped", "socket": str(state.socket_path)})
        return
    formatter.success(
        {
            "status": "running",
            "pid": ping.get("pid"),
            "started_at": ping.get("started_at"),
            "socket": str(state.socket_path),
        }
    )


@daemon.command("stop")
@click.pass_context
def daemon_stop(ctx):
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))
    state = build_daemon_state(ctx.obj.get("config_path"))
    stopped = stop_daemon(state)
    if not stopped:
        formatter.success({"status": "stopped", "changed": False})
        return
    formatter.success({"status": "stopped", "changed": True})
