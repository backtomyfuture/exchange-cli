from setuptools import find_packages


def test_package_discovery_only_includes_exchange_cli():
    packages = find_packages(include=["exchange_cli*"])

    assert packages
    assert all(name == "exchange_cli" or name.startswith("exchange_cli.") for name in packages)
    assert "tests" not in packages
    assert "docs" not in packages
    assert "npm" not in packages


def test_node_wrapper_reports_structured_json_on_missing_binary():
    import json
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    repo_root = Path(__file__).resolve().parents[1]
    wrapper = repo_root / "npm" / "exchange-cli" / "bin" / "exchange-cli.js"
    res = subprocess.run(
        [node, str(wrapper), "--help"],
        env={"PATH": "", "EXCHANGE_CLI_BINARY": "/nonexistent/binary/path"},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    data = json.loads(res.stdout)
    assert data["ok"] is False
    assert data["code"] == "BINARY_NOT_FOUND"
    assert data["retryable"] is False
