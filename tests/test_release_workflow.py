from pathlib import Path


def test_release_builds_every_platform_before_any_publish():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    build_section, publish_section = workflow.split("  publish-npm:", maxsplit=1)

    assert "npm publish" not in build_section
    assert "actions/upload-artifact@v4" in build_section
    assert "actions/download-artifact@v4" in publish_section
    assert "Expected 6 platform tarballs" in publish_section
    assert publish_section.index("Publish all platform packages") < publish_section.index(
        "Publish main package last"
    )


def test_npm_token_is_scoped_to_publish_job():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    build_section, publish_section = workflow.split("  publish-npm:", maxsplit=1)

    assert "NPM_TOKEN" not in build_section
    assert "NPM_TOKEN" in publish_section


def test_publish_job_uses_integrity_checked_idempotent_script_for_every_package():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    _, publish_section = workflow.split("  publish-npm:", maxsplit=1)
    script = "python scripts/publish_npm_tarballs.py"

    assert publish_section.count(script) == 2
    assert f"{script} release-artifacts/platforms/*.tgz" in publish_section
    assert f"{script} release-artifacts/main/*.tgz" in publish_section
    assert publish_section.index("release-artifacts/platforms/*.tgz") < publish_section.index(
        "Publish main package last"
    )
