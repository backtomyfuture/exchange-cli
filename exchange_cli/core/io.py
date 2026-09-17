"""Shared file and body-input helpers."""

from __future__ import annotations

import os
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


def read_binary_file(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CliError(
            f"Could not read file: {path}.",
            code="INVALID_INPUT",
            exit_code=2,
        ) from exc


def write_new_binary_file(path: Path, data: bytes) -> Path:
    """Write an explicit local output path without replacing an existing file."""

    output_path = path.expanduser()
    try:
        output_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise CliError(
            f"Could not create output directory: {output_path.parent}.",
            code="OUTPUT_WRITE_FAILED",
        ) from exc

    try:
        descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise CliError(
            f"Output file already exists: {output_path}.",
            code="OUTPUT_EXISTS",
            details={"path": str(output_path)},
        ) from exc
    except OSError as exc:
        raise CliError(
            f"Could not create output file: {output_path}.",
            code="OUTPUT_WRITE_FAILED",
        ) from exc

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except OSError as exc:
        output_path.unlink(missing_ok=True)
        raise CliError(
            f"Could not write output file: {output_path}.",
            code="OUTPUT_WRITE_FAILED",
        ) from exc
    return output_path


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
