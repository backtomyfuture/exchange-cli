"""Shared file and body-input helpers."""

from __future__ import annotations

from pathlib import Path

from .errors import CliError


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(
            f"Could not read file: {path}.",
            code="INVALID_INPUT",
            exit_code=2,
        ) from exc


def resolve_body(body: str | None, body_file: Path | None, *, required: bool = True) -> str | None:
    if body_file is not None:
        body = read_text_file(body_file)
    if required and not body:
        raise CliError(
            "Either --body or --body-file is required",
            code="INVALID_INPUT",
            exit_code=2,
        )
    return body
