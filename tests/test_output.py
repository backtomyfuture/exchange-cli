import io
import json

from exchange_cli.core.output import OutputFormatter


class TestOutputFormatter:
    def test_json_success_single(self):
        formatter = OutputFormatter("json")
        buf = io.StringIO()
        formatter.success({"id": "123", "subject": "Hi"}, file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": True, "data": {"id": "123", "subject": "Hi"}}

    def test_json_success_list(self):
        formatter = OutputFormatter("json")
        buf = io.StringIO()
        items = [{"id": "1"}, {"id": "2"}]
        formatter.success(items, count=2, file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": True, "count": 2, "data": items}

    def test_json_error(self):
        formatter = OutputFormatter("json")
        buf = io.StringIO()
        formatter.error("Connection failed", code="CONNECTION_ERROR", file=buf)
        data = json.loads(buf.getvalue())
        assert data == {"ok": False, "error": "Connection failed", "code": "CONNECTION_ERROR"}

    def test_json_error_with_retry_metadata(self):
        formatter = OutputFormatter("json")
        buf = io.StringIO()
        formatter.error(
            "Connection failed",
            code="CONNECTION_ERROR",
            retryable=True,
            details={"stage": "connect"},
            file=buf,
        )
        data = json.loads(buf.getvalue())
        assert data == {
            "ok": False,
            "error": "Connection failed",
            "code": "CONNECTION_ERROR",
            "retryable": True,
            "details": {"stage": "connect"},
        }

    def test_text_success_single(self):
        formatter = OutputFormatter("text")
        buf = io.StringIO()
        formatter.success({"subject": "Hi", "sender": "boss@x.com"}, file=buf)
        output = buf.getvalue()
        assert "subject" in output
        assert "Hi" in output

    def test_text_success_list(self):
        formatter = OutputFormatter("text")
        buf = io.StringIO()
        items = [{"subject": "A", "sender": "a@x.com"}, {"subject": "B", "sender": "b@x.com"}]
        formatter.success(items, count=2, file=buf)
        output = buf.getvalue()
        assert "A" in output
        assert "B" in output

    def test_text_error(self):
        formatter = OutputFormatter("text")
        buf = io.StringIO()
        formatter.error("Auth failed", code="AUTH_ERROR", file=buf)
        output = buf.getvalue()
        assert "Auth failed" in output

    def test_json_diagnostic_failure_contains_check_results(self):
        formatter = OutputFormatter("json")
        buf = io.StringIO()
        report = {"overall": "fail", "checks": [{"id": "ews_root", "status": "fail"}]}

        formatter.diagnostic(
            report,
            ok=False,
            error="Authentication failed",
            code="AUTH_ERROR",
            retryable=False,
            file=buf,
        )

        assert json.loads(buf.getvalue()) == {
            "ok": False,
            "error": "Authentication failed",
            "code": "AUTH_ERROR",
            "retryable": False,
            "data": report,
        }

    def test_text_diagnostic_includes_check_and_remediation(self):
        formatter = OutputFormatter("text")
        buf = io.StringIO()

        formatter.diagnostic(
            {
                "overall": "warn",
                "checks": [
                    {
                        "id": "tls_verification",
                        "status": "warn",
                        "message": "TLS certificate verification is disabled.",
                        "remediation": "Enable certificate verification when possible.",
                    }
                ],
            },
            file=buf,
        )

        assert buf.getvalue() == (
            "Doctor: WARN\n"
            "WARN tls_verification: TLS certificate verification is disabled.\n"
            "  Fix: Enable certificate verification when possible.\n"
        )
