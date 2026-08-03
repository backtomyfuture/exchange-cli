"""Top-level diagnostic command for exchange-cli."""

import click

from ..core.config import ConfigManager
from ..core.connection import probe_connection
from ..core.errors import CliError, classify_exception
from ..core.output import OutputFormatter


def _remediation(code: str) -> str:
    remediation_by_code = {
        "CONFIG_NOT_FOUND": "Run: exchange-cli config init",
        "CONFIG_KEY_MISSING": "Restore the existing configuration key before retrying.",
        "CONFIG_DECRYPT_FAILED": "Restore the existing configuration key before retrying.",
        "AUTH_ERROR": "Verify the configured credentials with your Exchange administrator.",
        "CONNECTION_ERROR": "Verify network reachability and the Exchange server, then retry.",
        "TIMEOUT_ERROR": "Verify network reachability and the Exchange server, then retry.",
        "SERVER_BUSY": "Retry after the Exchange server is available.",
    }
    return remediation_by_code.get(code, "Review the reported configuration and retry.")


def _overall_status(checks: list[dict]) -> str:
    if any(check["status"] == "fail" for check in checks):
        return "fail"
    if any(check["status"] == "warn" for check in checks):
        return "warn"
    return "pass"


def _failed_check(check_id: str, error: CliError) -> dict:
    return {
        "id": check_id,
        "status": "fail",
        "message": error.message,
        "code": error.code,
        "remediation": _remediation(error.code),
    }


def _emit_failure(formatter: OutputFormatter, checks: list[dict], error: CliError) -> None:
    formatter.diagnostic(
        {"overall": _overall_status(checks), "checks": checks},
        ok=False,
        error=error.message,
        code=error.code,
        retryable=error.retryable,
    )
    raise SystemExit(error.exit_code)


@click.command("doctor")
@click.option("--offline", is_flag=True, help="Skip the EWS connection probe.")
@click.pass_context
def doctor(ctx, offline):
    """Diagnose effective configuration, TLS safety, and EWS connectivity."""

    config_path = ctx.obj.get("config_path")
    account_email = ctx.obj.get("account_email")
    config_manager = ConfigManager(config_dir=config_path) if config_path else ConfigManager()
    formatter = OutputFormatter(ctx.obj.get("fmt", "json"))

    try:
        credentials = config_manager.get_account_credentials(account_email)
        if not credentials:
            raise CliError("No configuration found. Run: exchange-cli config init", code="CONFIG_NOT_FOUND")
    except Exception as exc:
        error = classify_exception(exc)
        checks = [
            _failed_check("effective_config", error),
            {
                "id": "tls_verification",
                "status": "skipped",
                "message": "Skipped because effective configuration is unavailable.",
            },
            {
                "id": "ews_root",
                "status": "skipped",
                "message": "Skipped because effective configuration is unavailable.",
            },
        ]
        _emit_failure(formatter, checks, error)

    checks = [{"id": "effective_config", "status": "pass"}]
    if credentials["no_verify_ssl"]:
        checks.append(
            {
                "id": "tls_verification",
                "status": "warn",
                "message": "TLS certificate verification is disabled.",
                "remediation": "Enable certificate verification when possible.",
            }
        )
    else:
        checks.append({"id": "tls_verification", "status": "pass"})

    if offline:
        checks.append(
            {
                "id": "ews_root",
                "status": "skipped",
                "message": "Skipped because --offline was requested.",
            }
        )
        formatter.diagnostic({"overall": _overall_status(checks), "checks": checks})
        return

    try:
        if not probe_connection(credentials):
            raise CliError("Connection failed.", code="CONNECTION_ERROR", retryable=True)
    except Exception as exc:
        error = classify_exception(exc)
        checks.append(_failed_check("ews_root", error))
        _emit_failure(formatter, checks, error)

    checks.append({"id": "ews_root", "status": "pass"})
    formatter.diagnostic({"overall": _overall_status(checks), "checks": checks})
