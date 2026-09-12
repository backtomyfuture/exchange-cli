from pathlib import Path

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
        "INSECURE_TLS": (
            "Enable certificate verification. Use server domain name or configure ca_bundle / REQUESTS_CA_BUNDLE."
        ),
        "CA_BUNDLE_NOT_FOUND": "Verify that the configured ca_bundle path exists and is readable.",
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
        server = str(credentials.get("server", ""))
        parts = server.split(".")
        is_ip = len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
        ip_hint = " Note: using an IP address often causes TLS certificate mismatch." if is_ip else ""
        remediation = (
            f"Enable certificate verification.{ip_hint} "
            "Use the server domain name or configure ca_bundle / REQUESTS_CA_BUNDLE."
        )
        checks.append(
            {
                "id": "tls_verification",
                "status": "fail",
                "message": "TLS certificate verification is disabled.",
                "code": "INSECURE_TLS",
                "remediation": remediation,
            }
        )
    elif credentials.get("ca_bundle"):
        ca_path = Path(credentials["ca_bundle"]).expanduser()
        if not ca_path.is_file():
            checks.append(
                {
                    "id": "tls_verification",
                    "status": "fail",
                    "message": f"Configured CA bundle file not found: {credentials['ca_bundle']}",
                    "code": "CA_BUNDLE_NOT_FOUND",
                    "remediation": "Verify that the ca_bundle path exists and is readable.",
                }
            )
        else:
            checks.append(
                {
                    "id": "tls_verification",
                    "status": "pass",
                    "message": f"TLS certificate verification enabled with CA bundle: {credentials['ca_bundle']}",
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
        if _overall_status(checks) == "fail":
            failed = next(c for c in checks if c["status"] == "fail")
            formatter.diagnostic(
                {"overall": "fail", "checks": checks},
                ok=False,
                error=failed.get("message", "Doctor checks failed."),
                code=failed.get("code", "DIAGNOSTIC_FAILURE"),
            )
            raise SystemExit(1)
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
    if _overall_status(checks) == "fail":
        failed = next(c for c in checks if c["status"] == "fail")
        formatter.diagnostic(
            {"overall": "fail", "checks": checks},
            ok=False,
            error=failed.get("message", "Doctor checks failed."),
            code=failed.get("code", "DIAGNOSTIC_FAILURE"),
        )
        raise SystemExit(1)
    formatter.diagnostic({"overall": _overall_status(checks), "checks": checks})
