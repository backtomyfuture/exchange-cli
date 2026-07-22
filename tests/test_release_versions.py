import json

import pytest

from scripts.check_release_versions import (
    EXPECTED_PLATFORMS,
    MAIN_PACKAGE_NAME,
    check_versions,
    platform_package_name,
)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def release_tree(tmp_path):
    version = "1.2.3"
    init_path = tmp_path / "exchange_cli" / "__init__.py"
    init_path.parent.mkdir()
    init_path.write_text(f'__version__ = "{version}"\n', encoding="utf-8")

    dependencies = {}
    for platform, expected in EXPECTED_PLATFORMS.items():
        platform_dir = tmp_path / "npm" / "platforms" / platform
        _write_json(
            platform_dir / "package.json",
            {
                "name": platform_package_name(platform),
                "version": version,
                "os": [expected["os"]],
                "cpu": [expected["cpu"]],
            },
        )
        (platform_dir / "entrypoint.py").write_text("# entrypoint\n", encoding="utf-8")
        dependencies[platform_package_name(platform)] = version

    _write_json(
        tmp_path / "npm" / "exchange-cli" / "package.json",
        {
            "name": MAIN_PACKAGE_NAME,
            "version": version,
            "optionalDependencies": dependencies,
        },
    )
    return tmp_path


def test_complete_release_contract_passes(release_tree):
    version, errors = check_versions(release_tree, tag="v1.2.3")

    assert version == "1.2.3"
    assert errors == []


def test_missing_platform_manifest_is_reported(release_tree):
    (release_tree / "npm" / "platforms" / "linux-x64" / "package.json").unlink()

    _, errors = check_versions(release_tree)

    assert any("missing platform manifests: linux-x64" in error for error in errors)


def test_unexpected_platform_manifest_is_reported(release_tree):
    unexpected = release_tree / "npm" / "platforms" / "freebsd-x64"
    _write_json(unexpected / "package.json", {"version": "1.2.3"})

    _, errors = check_versions(release_tree)

    assert any("unexpected platform manifests: freebsd-x64" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", "wrong", "name expected"),
        ("version", "9.9.9", "version expected"),
        ("os", ["linux"], "os expected"),
        ("cpu", ["x64"], "cpu expected"),
    ],
)
def test_platform_manifest_metadata_is_checked(release_tree, field, value, message):
    manifest_path = release_tree / "npm" / "platforms" / "darwin-arm64" / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    _write_json(manifest_path, manifest)

    _, errors = check_versions(release_tree)

    assert any("darwin-arm64/package.json" in error and message in error for error in errors)


def test_missing_entrypoint_is_reported(release_tree):
    (release_tree / "npm" / "platforms" / "linux-arm64" / "entrypoint.py").unlink()

    _, errors = check_versions(release_tree)

    assert any("linux-arm64/entrypoint.py: entrypoint is missing" in error for error in errors)


@pytest.mark.parametrize("mutation", ["missing", "unexpected", "wrong_version"])
def test_optional_dependencies_are_exact(release_tree, mutation):
    manifest_path = release_tree / "npm" / "exchange-cli" / "package.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dependencies = manifest["optionalDependencies"]
    if mutation == "missing":
        dependencies.pop(platform_package_name("linux-x64"))
    elif mutation == "unexpected":
        dependencies["@backtomyfuture/exchange-cli-freebsd-x64"] = "1.2.3"
    else:
        dependencies[platform_package_name("linux-x64")] = "1.2.2"
    _write_json(manifest_path, manifest)

    _, errors = check_versions(release_tree)

    assert errors
    assert any("optionalDependencies" in error or "exchange-cli-linux-x64" in error for error in errors)


def test_tag_must_match_exact_v_version(release_tree):
    _, errors = check_versions(release_tree, tag="1.2.3")

    assert errors == ["Git tag: expected v1.2.3, found 1.2.3"]


def test_invalid_manifest_json_is_reported_without_traceback(release_tree):
    manifest_path = release_tree / "npm" / "exchange-cli" / "package.json"
    manifest_path.write_text("{broken", encoding="utf-8")

    _, errors = check_versions(release_tree)

    assert len(errors) == 1
    assert "invalid JSON" in errors[0]
