#!/usr/bin/env python3
"""Verify the complete Python/npm release contract before publishing."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

MAIN_PACKAGE_NAME = "@backtomyfuture/exchange-cli"
EXPECTED_PLATFORMS = {
    "darwin-arm64": {"os": "darwin", "cpu": "arm64"},
    "darwin-x64": {"os": "darwin", "cpu": "x64"},
    "linux-arm64": {"os": "linux", "cpu": "arm64"},
    "linux-x64": {"os": "linux", "cpu": "x64"},
    "win32-ia32": {"os": "win32", "cpu": "ia32"},
    "win32-x64": {"os": "win32", "cpu": "x64"},
}


def platform_package_name(platform: str) -> str:
    return f"{MAIN_PACKAGE_NAME}-{platform}"


def read_python_version(repo_root: Path) -> str:
    init_path = repo_root / "exchange_cli" / "__init__.py"
    module = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            continue
        value = ast.literal_eval(node.value)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"Could not find a string __version__ assignment in {init_path}")


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _read_manifest(path: Path, repo_root: Path, errors: list[str]) -> dict[str, Any] | None:
    relative_path = _relative(path, repo_root)
    if not path.is_file():
        errors.append(f"{relative_path}: manifest is missing")
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{relative_path}: manifest is unreadable or invalid JSON ({exc})")
        return None
    if not isinstance(manifest, dict):
        errors.append(f"{relative_path}: manifest root must be an object")
        return None
    return manifest


def _check_platform_set(repo_root: Path, errors: list[str]) -> None:
    platforms_root = repo_root / "npm" / "platforms"
    actual = {
        child.name
        for child in platforms_root.iterdir()
        if child.is_dir() and (child / "package.json").exists()
    } if platforms_root.is_dir() else set()
    expected = set(EXPECTED_PLATFORMS)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if missing:
        errors.append(f"npm/platforms: missing platform manifests: {', '.join(missing)}")
    if unexpected:
        errors.append(f"npm/platforms: unexpected platform manifests: {', '.join(unexpected)}")


def _check_platform_manifests(repo_root: Path, version: str, errors: list[str]) -> None:
    for platform, expected in EXPECTED_PLATFORMS.items():
        platform_dir = repo_root / "npm" / "platforms" / platform
        manifest_path = platform_dir / "package.json"
        manifest = _read_manifest(manifest_path, repo_root, errors)
        if manifest is None:
            continue
        relative_path = _relative(manifest_path, repo_root)
        checks = {
            "name": platform_package_name(platform),
            "version": version,
            "os": [expected["os"]],
            "cpu": [expected["cpu"]],
        }
        for field, expected_value in checks.items():
            actual_value = manifest.get(field)
            if actual_value != expected_value:
                errors.append(
                    f"{relative_path}: {field} expected {expected_value!r}, found {actual_value!r}"
                )
        entrypoint = platform_dir / "entrypoint.py"
        if not entrypoint.is_file():
            errors.append(f"{_relative(entrypoint, repo_root)}: entrypoint is missing")


def _check_main_manifest(repo_root: Path, version: str, errors: list[str]) -> None:
    manifest_path = repo_root / "npm" / "exchange-cli" / "package.json"
    manifest = _read_manifest(manifest_path, repo_root, errors)
    if manifest is None:
        return
    relative_path = _relative(manifest_path, repo_root)
    if manifest.get("name") != MAIN_PACKAGE_NAME:
        errors.append(
            f"{relative_path}: name expected {MAIN_PACKAGE_NAME!r}, found {manifest.get('name')!r}"
        )
    if manifest.get("version") != version:
        errors.append(
            f"{relative_path}: version expected {version!r}, found {manifest.get('version')!r}"
        )

    dependencies = manifest.get("optionalDependencies")
    if not isinstance(dependencies, dict):
        errors.append(f"{relative_path}: optionalDependencies must be an object")
        return
    expected_names = {platform_package_name(platform) for platform in EXPECTED_PLATFORMS}
    actual_names = set(dependencies)
    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names)
    if missing:
        errors.append(f"{relative_path}: missing optionalDependencies: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{relative_path}: unexpected optionalDependencies: {', '.join(unexpected)}")
    for dependency in sorted(expected_names & actual_names):
        if dependencies[dependency] != version:
            errors.append(
                f"{relative_path}: {dependency} expected {version!r}, found {dependencies[dependency]!r}"
            )


def check_versions(repo_root: Path, tag: str | None = None) -> tuple[str, list[str]]:
    errors: list[str] = []
    try:
        version = read_python_version(repo_root)
    except (OSError, SyntaxError, TypeError, ValueError) as exc:
        return "unknown", [f"exchange_cli/__init__.py: could not read Python version ({exc})"]

    _check_platform_set(repo_root, errors)
    _check_platform_manifests(repo_root, version, errors)
    _check_main_manifest(repo_root, version, errors)

    if tag and tag != f"v{version}":
        errors.append(f"Git tag: expected v{version}, found {tag}")
    return version, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Optional release tag to verify (for example, v0.1.10)")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    version, errors = check_versions(repo_root, tag=args.tag)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print(f"Release contract is complete and synchronized: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
