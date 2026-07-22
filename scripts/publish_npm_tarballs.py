#!/usr/bin/env python3
"""Publish npm tarballs idempotently, rejecting changed bytes for an existing version."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REGISTRY = "https://registry.npmjs.org"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REGISTRY_RESPONSE_BYTES = 4 * 1024 * 1024


class PublishError(RuntimeError):
    """A release safety check or npm publish operation failed."""


@dataclass(frozen=True)
class PackageTarball:
    path: Path
    name: str
    version: str
    integrity: str


def _read_limited(stream: Any, limit: int, description: str) -> bytes:
    payload = stream.read(limit + 1)
    if len(payload) > limit:
        raise PublishError(f"{description} exceeds the {limit}-byte safety limit")
    return payload


def _sha512_sri(path: Path) -> str:
    digest = hashlib.sha512()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PublishError(f"Could not read tarball {path}: {exc}") from exc
    encoded = base64.b64encode(digest.digest()).decode("ascii")
    return f"sha512-{encoded}"


def inspect_tarball(path: Path) -> PackageTarball:
    """Read npm package identity and exact-byte integrity without extracting the archive."""
    if not path.is_file():
        raise PublishError(f"Tarball does not exist or is not a file: {path}")

    try:
        with tarfile.open(path, mode="r:gz") as archive:
            manifests = [
                member
                for member in archive.getmembers()
                if member.name in {"package/package.json", "./package/package.json"}
            ]
            if len(manifests) != 1 or not manifests[0].isfile():
                raise PublishError(
                    f"{path}: expected exactly one regular package/package.json member"
                )
            manifest_stream = archive.extractfile(manifests[0])
            if manifest_stream is None:
                raise PublishError(f"{path}: could not read package/package.json")
            manifest_bytes = _read_limited(
                manifest_stream,
                MAX_MANIFEST_BYTES,
                f"{path}: package/package.json",
            )
    except PublishError:
        raise
    except (OSError, tarfile.TarError) as exc:
        raise PublishError(f"Could not inspect npm tarball {path}: {exc}") from exc

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishError(f"{path}: package/package.json is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise PublishError(f"{path}: package/package.json root must be an object")

    name = manifest.get("name")
    version = manifest.get("version")
    if not isinstance(name, str) or not name.strip():
        raise PublishError(f"{path}: package.json name must be a non-empty string")
    if not isinstance(version, str) or not version.strip():
        raise PublishError(f"{path}: package.json version must be a non-empty string")
    return PackageTarball(
        path=path,
        name=name,
        version=version,
        integrity=_sha512_sri(path),
    )


def _registry_version_url(registry: str, name: str, version: str) -> str:
    encoded_name = urllib.parse.quote(name, safe="@")
    encoded_version = urllib.parse.quote(version, safe="")
    return f"{registry.rstrip('/')}/{encoded_name}/{encoded_version}"


def query_published_integrity(package: PackageTarball, registry: str) -> str | None:
    """Return published dist.integrity, or None only when this exact version is absent."""
    url = _registry_version_url(registry, package.name, package.version)
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "exchange-cli-release"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = _read_limited(
                response,
                MAX_REGISTRY_RESPONSE_BYTES,
                f"Registry response for {package.name}@{package.version}",
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise PublishError(
            f"Registry query failed for {package.name}@{package.version}: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise PublishError(
            f"Registry query failed for {package.name}@{package.version}: {exc.reason}"
        ) from exc
    except OSError as exc:
        raise PublishError(
            f"Registry query failed for {package.name}@{package.version}: {exc}"
        ) from exc

    try:
        metadata = json.loads(payload.decode("utf-8"))
        integrity = metadata["dist"]["integrity"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise PublishError(
            f"Registry metadata for {package.name}@{package.version} has no valid dist.integrity"
        ) from exc
    if not isinstance(integrity, str) or not integrity:
        raise PublishError(
            f"Registry metadata for {package.name}@{package.version} has no valid dist.integrity"
        )
    return integrity


def publish_tarballs(paths: list[Path], registry: str = DEFAULT_REGISTRY) -> None:
    """Process tarballs in argument order, publishing only versions absent from npm."""
    for path in paths:
        package = inspect_tarball(path)
        published_integrity = query_published_integrity(package, registry)
        identity = f"{package.name}@{package.version}"

        if published_integrity is not None:
            if published_integrity != package.integrity:
                raise PublishError(
                    f"Refusing to skip {identity}: local integrity {package.integrity} "
                    f"does not match registry integrity {published_integrity}"
                )
            print(f"Already published with matching integrity; skipping {identity}")
            continue

        print(f"Publishing {identity} from {package.path}")
        try:
            subprocess.run(
                [
                    "npm",
                    "publish",
                    str(package.path),
                    "--access",
                    "public",
                    "--registry",
                    registry,
                ],
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise PublishError(f"npm publish failed for {identity}: {exc}") from exc


def _valid_registry(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError("registry must be an absolute HTTP(S) URL")
    return value.rstrip("/")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tarballs", nargs="+", type=Path, help="npm .tgz files in publish order")
    parser.add_argument("--registry", type=_valid_registry, default=DEFAULT_REGISTRY)
    args = parser.parse_args(argv)

    try:
        publish_tarballs(args.tarballs, registry=args.registry)
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
