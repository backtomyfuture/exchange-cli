#!/usr/bin/env python3
"""Build and stage npm platform package payload for any supported platform."""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SUPPORTED_PLATFORMS = [
    "darwin-arm64",
    "darwin-x64",
    "linux-x64",
    "linux-arm64",
    "win32-x64",
    "win32-ia32",
]

HIDDEN_IMPORTS = [
    "exchange_cli.commands.calendar",
    "exchange_cli.commands.config",
    "exchange_cli.commands.contact",
    "exchange_cli.commands.daemon",
    "exchange_cli.commands.draft",
    "exchange_cli.commands.email",
    "exchange_cli.commands.folder",
    "exchange_cli.commands.task",
    "markdownify",
    "bs4",
]


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def _count_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def _is_windows(platform: str) -> bool:
    return platform.startswith("win32")


def _is_darwin(platform: str) -> bool:
    return platform.startswith("darwin")


def _is_linux(platform: str) -> bool:
    return platform.startswith("linux")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare npm/platforms/<platform>/bin payload from PyInstaller dist")
    parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS, help="Target platform (e.g. darwin-arm64)")
    parser.add_argument("--skip-build", action="store_true", help="Do not rebuild dist/ via pyinstaller")
    args = parser.parse_args()

    platform: str = args.platform
    repo_root = Path(__file__).resolve().parents[1]
    entrypoint = repo_root / "npm" / "platforms" / platform / "entrypoint.py"
    dist_dir = repo_root / "dist" / "exchange-cli"
    target_dir = repo_root / "npm" / "platforms" / platform / "bin"

    binary_name = "exchange-cli.exe" if _is_windows(platform) else "exchange-cli"
    binary_path = target_dir / binary_name

    # ── Build ────────────────────────────────────────────────────────
    if not args.skip_build:
        if not entrypoint.exists():
            raise FileNotFoundError(f"Entrypoint does not exist: {entrypoint}")

        cmd: list[str] = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            "--name", "exchange-cli",
            "--console",
            "--collect-all", "exchangelib",
        ]
        for mod in HIDDEN_IMPORTS:
            cmd += ["--hidden-import", mod]
        cmd.append(str(entrypoint))

        _run(cmd, cwd=repo_root)

    # ── Stage ────────────────────────────────────────────────────────
    if not dist_dir.exists():
        raise FileNotFoundError(f"Expected dist directory does not exist: {dist_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)

    # symlinks=False materializes symlink targets as plain files.
    # This avoids npm install link-loss issues in global node_modules.
    shutil.copytree(dist_dir, target_dir, symlinks=False, copy_function=shutil.copy2)

    # ── Verify binary ────────────────────────────────────────────────
    if not binary_path.exists():
        raise FileNotFoundError(f"Expected binary does not exist: {binary_path}")

    if not _is_windows(platform):
        binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # ── Platform-specific verification ───────────────────────────────
    if _is_darwin(platform):
        python_runtime = target_dir / "_internal" / "Python"
        if not python_runtime.exists():
            raise FileNotFoundError(f"Expected runtime library missing after staging: {python_runtime}")
        print(f"Verified runtime library: {python_runtime}")

    if _is_linux(platform):
        internal_dir = target_dir / "_internal"
        if not internal_dir.exists():
            raise FileNotFoundError(f"Expected _internal directory missing after staging: {internal_dir}")
        print(f"Verified _internal directory: {internal_dir}")

    # ── Summary ──────────────────────────────────────────────────────
    file_count = _count_files(target_dir)
    print(f"Platform:  {platform}")
    print(f"Binary:    {binary_path}")
    print(f"Staged {file_count} files into {target_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
