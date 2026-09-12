#!/usr/bin/env python3
"""Generate Formula/exchange-cli.rb from staged GitHub Release archives."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

REPO = "backtomyfuture/exchange-cli"
HOMEPAGE = f"https://github.com/{REPO}"

UNIX_PLATFORMS = ("darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset(assets_dir: Path, platform: str) -> tuple[str, str]:
    path = assets_dir / f"exchange-cli-{platform}.tar.gz"
    if not path.is_file():
        raise FileNotFoundError(path)
    url = f"https://github.com/{REPO}/releases/download/v{{version}}/{path.name}"
    return url, _sha256(path)


def render_formula(version: str, assets_dir: Path) -> str:
    urls = {platform: _asset(assets_dir, platform) for platform in UNIX_PLATFORMS}
    darwin_arm_url, darwin_arm_sha = urls["darwin-arm64"]
    darwin_x64_url, darwin_x64_sha = urls["darwin-x64"]
    linux_arm_url, linux_arm_sha = urls["linux-arm64"]
    linux_x64_url, linux_x64_sha = urls["linux-x64"]
    return f'''class ExchangeCli < Formula
  desc "CLI for on-premises Microsoft Exchange Server"
  homepage "{HOMEPAGE}"
  version "{version}"
  license "Apache-2.0"

  on_macos do
    on_arm do
      url "{darwin_arm_url.format(version=version)}"
      sha256 "{darwin_arm_sha}"
    end
    on_intel do
      url "{darwin_x64_url.format(version=version)}"
      sha256 "{darwin_x64_sha}"
    end
  end

  on_linux do
    on_arm do
      url "{linux_arm_url.format(version=version)}"
      sha256 "{linux_arm_sha}"
    end
    on_intel do
      url "{linux_x64_url.format(version=version)}"
      sha256 "{linux_x64_sha}"
    end
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"exchange-cli"
  end

  test do
    assert_match version.to_s, shell_output("#{{bin}}/exchange-cli --version")
  end
end
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--assets-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    formula = render_formula(args.version, args.assets_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(formula, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
