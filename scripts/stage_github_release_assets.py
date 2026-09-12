#!/usr/bin/env python3
"""Turn npm platform tarballs into GitHub Release / Homebrew archives."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import zipfile
from pathlib import Path

PLATFORM_NAMES = {
    "darwin-arm64": "darwin-arm64",
    "darwin-x64": "darwin-x64",
    "linux-arm64": "linux-arm64",
    "linux-x64": "linux-x64",
    "win32-ia32": "win32-ia32",
    "win32-x64": "win32-x64",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_bin_dir(tarball: Path, work_dir: Path) -> Path:
    extract_root = work_dir / tarball.stem
    extract_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as archive:
        archive.extractall(extract_root, filter="data")
    candidates = [path for path in extract_root.rglob("bin") if path.is_dir()]
    for candidate in candidates:
        if (candidate / "exchange-cli").exists() or (candidate / "exchange-cli.exe").exists():
            return candidate
    raise FileNotFoundError(f"{tarball} does not contain a staged bin directory")


def _detect_platform(tarball: Path) -> str:
    name = tarball.name
    for platform in PLATFORM_NAMES:
        if platform in name:
            return platform
    raise ValueError(f"Could not detect platform from {tarball.name}")


def _archive_unix(bin_dir: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(bin_dir.rglob("*")):
            archive.add(path, arcname=path.relative_to(bin_dir).as_posix())


def _archive_windows(bin_dir: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bin_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(bin_dir).as_posix())


def stage_assets(tarball_dir: Path, output_dir: Path, work_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    assets: list[Path] = []
    tarballs = sorted(tarball_dir.glob("*.tgz")) + sorted(tarball_dir.glob("*.tar.gz"))
    if not tarballs:
        raise FileNotFoundError(f"No platform tarballs found in {tarball_dir}")
    for tarball in tarballs:
        platform = _detect_platform(tarball)
        bin_dir = _extract_bin_dir(tarball, work_dir)
        if platform.startswith("win32"):
            destination = output_dir / f"exchange-cli-{platform}.zip"
            _archive_windows(bin_dir, destination)
        else:
            destination = output_dir / f"exchange-cli-{platform}.tar.gz"
            _archive_unix(bin_dir, destination)
        assets.append(destination)
    checksum_path = output_dir / "SHA256SUMS"
    lines = [f"{_sha256(path)}  {path.name}" for path in assets]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assets.append(checksum_path)
    return assets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tarball-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--work-dir", default=None, type=Path)
    args = parser.parse_args(argv)
    work_dir = args.work_dir or (args.output_dir / ".work")
    if work_dir.exists():
        shutil.rmtree(work_dir)
    assets = stage_assets(args.tarball_dir, args.output_dir, work_dir)
    for asset in assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
