import tarfile

from scripts.stage_github_release_assets import stage_assets
from scripts.write_homebrew_formula import render_formula


def test_stage_assets_and_formula(tmp_path):
    tarball_dir = tmp_path / "tarballs"
    tarball_dir.mkdir()
    for platform in ("darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64"):
        package = tmp_path / "src" / platform / "package" / "bin"
        package.mkdir(parents=True)
        (package / "exchange-cli").write_text("binary\n", encoding="utf-8")
        archive = tarball_dir / f"backtomyfuture-exchange-cli-{platform}-0.2.1.tgz"
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(package.parent.parent, arcname="package")

    output_dir = tmp_path / "out"
    assets = stage_assets(tarball_dir, output_dir, tmp_path / "work")
    names = {path.name for path in assets}
    assert "exchange-cli-darwin-arm64.tar.gz" in names
    assert "SHA256SUMS" in names
    formula = render_formula("0.2.1", output_dir)
    assert 'version "0.2.1"' in formula
    assert "on_macos" in formula
    assert "on_linux" in formula
    assert "assert_match version.to_s" in formula
