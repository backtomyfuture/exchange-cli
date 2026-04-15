#!/usr/bin/env python3
"""Build and stage npm darwin-arm64 package payload."""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=True)


def _count_files(root: Path) -> int:
    return sum(1 for path in root.rglob("*") if path.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare npm/platforms/darwin-arm64/bin payload from PyInstaller dist")
    parser.add_argument("--skip-build", action="store_true", help="Do not rebuild dist/ via pyinstaller")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = repo_root / "dist" / "exchange-cli"
    target_dir = repo_root / "npm" / "platforms" / "darwin-arm64" / "bin"
    binary_path = target_dir / "exchange-cli"

    if not args.skip_build:
        _run([sys.executable, "-m", "PyInstaller", "--noconfirm", "exchange-cli.spec"], cwd=repo_root)

    if not dist_dir.exists():
        raise FileNotFoundError(f"Expected dist directory does not exist: {dist_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)

    # IMPORTANT: symlinks=False materializes symlink targets as plain files.
    # This avoids npm install link-loss issues in global node_modules.
    shutil.copytree(dist_dir, target_dir, symlinks=False, copy_function=shutil.copy2)

    if not binary_path.exists():
        raise FileNotFoundError(f"Expected binary does not exist: {binary_path}")

    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    python_runtime = target_dir / "_internal" / "Python"
    if not python_runtime.exists():
        raise FileNotFoundError(f"Expected runtime library missing after staging: {python_runtime}")

    file_count = _count_files(target_dir)
    print(f"Staged {file_count} files into {target_dir}")
    print(f"Verified runtime library: {python_runtime}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
