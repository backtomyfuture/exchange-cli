import base64
import hashlib
import io
import json
import subprocess
import tarfile
import urllib.error
from pathlib import Path

import pytest

from scripts import publish_npm_tarballs
from scripts.publish_npm_tarballs import PublishError, inspect_tarball, publish_tarballs


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _make_tarball(tmp_path: Path, filename: str, name: str, version: str) -> Path:
    path = tmp_path / filename
    payload = json.dumps({"name": name, "version": version}).encode()
    member = tarfile.TarInfo("package/package.json")
    member.size = len(payload)
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))
    return path


def test_inspect_tarball_reads_identity_and_exact_byte_sri(tmp_path):
    path = _make_tarball(tmp_path, "one.tgz", "@scope/one", "1.2.3")

    package = inspect_tarball(path)

    expected = "sha512-" + base64.b64encode(hashlib.sha512(path.read_bytes()).digest()).decode()
    assert (package.name, package.version, package.integrity) == ("@scope/one", "1.2.3", expected)


def test_publish_tarballs_processes_unpublished_packages_in_argument_order(tmp_path, monkeypatch):
    first = _make_tarball(tmp_path, "first.tgz", "@scope/first", "1.0.0")
    second = _make_tarball(tmp_path, "second.tgz", "@scope/second", "1.0.0")
    queried = []
    published = []

    def fake_query(package, registry):
        queried.append((package.name, registry))
        return None

    def fake_run(command, check):
        assert check is True
        published.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(publish_npm_tarballs, "query_published_integrity", fake_query)
    monkeypatch.setattr(publish_npm_tarballs.subprocess, "run", fake_run)

    publish_tarballs([second, first])

    assert [name for name, _ in queried] == ["@scope/second", "@scope/first"]
    assert [Path(command[2]) for command in published] == [second, first]
    assert all(command[0:2] == ["npm", "publish"] for command in published)


def test_existing_version_with_matching_integrity_is_skipped(tmp_path, monkeypatch):
    path = _make_tarball(tmp_path, "same.tgz", "@scope/same", "1.0.0")
    expected = inspect_tarball(path).integrity
    monkeypatch.setattr(
        publish_npm_tarballs,
        "query_published_integrity",
        lambda package, registry: expected,
    )
    calls = []
    monkeypatch.setattr(
        publish_npm_tarballs.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(args),
    )

    publish_tarballs([path])

    assert calls == []


def test_existing_version_with_different_integrity_fails_before_later_tarballs(
    tmp_path, monkeypatch
):
    changed = _make_tarball(tmp_path, "changed.tgz", "@scope/changed", "1.0.0")
    later = _make_tarball(tmp_path, "later.tgz", "@scope/later", "1.0.0")
    queried = []

    def fake_query(package, registry):
        queried.append(package.name)
        return "sha512-registry-bytes"

    monkeypatch.setattr(publish_npm_tarballs, "query_published_integrity", fake_query)
    monkeypatch.setattr(
        publish_npm_tarballs.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("must not publish on an integrity mismatch"),
    )

    with pytest.raises(PublishError, match="does not match registry integrity"):
        publish_tarballs([changed, later])

    assert queried == ["@scope/changed"]


def test_registry_404_means_version_is_unpublished(tmp_path, monkeypatch):
    path = _make_tarball(tmp_path, "missing.tgz", "@scope/missing", "1.0.0")
    package = inspect_tarball(path)
    requested_urls = []

    def fake_urlopen(request, timeout):
        requested_urls.append((request.full_url, timeout))
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(publish_npm_tarballs.urllib.request, "urlopen", fake_urlopen)

    assert publish_npm_tarballs.query_published_integrity(package, "https://registry.example") is None
    assert requested_urls == [
        ("https://registry.example/@scope%2Fmissing/1.0.0", 30)
    ]


def test_registry_integrity_is_returned_verbatim(tmp_path, monkeypatch):
    path = _make_tarball(tmp_path, "published.tgz", "plain-package", "1.0.0")
    package = inspect_tarball(path)
    monkeypatch.setattr(
        publish_npm_tarballs.urllib.request,
        "urlopen",
        lambda request, timeout: _Response(b'{"dist":{"integrity":"sha512-ExactValue=="}}'),
    )

    assert (
        publish_npm_tarballs.query_published_integrity(package, "https://registry.example")
        == "sha512-ExactValue=="
    )


def test_registry_metadata_without_integrity_is_rejected(tmp_path, monkeypatch):
    path = _make_tarball(tmp_path, "bad-metadata.tgz", "plain-package", "1.0.0")
    package = inspect_tarball(path)

    monkeypatch.setattr(
        publish_npm_tarballs.urllib.request,
        "urlopen",
        lambda request, timeout: _Response(b'{"dist": {}}'),
    )

    with pytest.raises(PublishError, match="no valid dist.integrity"):
        publish_npm_tarballs.query_published_integrity(package, "https://registry.example")


def test_main_reports_publish_errors_without_traceback(tmp_path, capsys):
    missing = tmp_path / "missing.tgz"

    assert publish_npm_tarballs.main([str(missing)]) == 1
    assert "ERROR: Tarball does not exist" in capsys.readouterr().err
