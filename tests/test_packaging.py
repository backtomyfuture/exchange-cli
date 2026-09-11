from setuptools import find_packages


def test_package_discovery_only_includes_exchange_cli():
    packages = find_packages(include=["exchange_cli*"])

    assert packages
    assert all(name == "exchange_cli" or name.startswith("exchange_cli.") for name in packages)
    assert "tests" not in packages
    assert "docs" not in packages
    assert "npm" not in packages
