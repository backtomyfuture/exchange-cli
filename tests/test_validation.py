import stat

import pytest
from exchangelib import FileAttachment

from exchange_cli.core.errors import CliError
from exchange_cli.core.validation import (
    ensure_start_before_end,
    normalize_folder,
    require_confirmation,
    save_file_attachments,
    validate_bounded_int,
)


def test_normalize_folder_is_case_insensitive():
    assert normalize_folder("INBOX") == "inbox"


def test_normalize_folder_rejects_unknown_name():
    with pytest.raises(CliError, match="Unsupported folder") as caught:
        normalize_folder("calendar")

    assert caught.value.code == "INVALID_FOLDER"
    assert caught.value.exit_code == 2


@pytest.mark.parametrize("value", [0, 201, True, 1.5, "many"])
def test_validate_bounded_int_rejects_invalid_values(value):
    with pytest.raises(CliError) as caught:
        validate_bounded_int(value, field="limit", minimum=1, maximum=200)

    assert caught.value.code == "INVALID_INPUT"


def test_ensure_start_before_end_rejects_reversed_range():
    with pytest.raises(CliError) as caught:
        ensure_start_before_end(2, 1, action="search")

    assert caught.value.code == "INVALID_TIME_RANGE"


def test_require_confirmation_has_machine_readable_details():
    with pytest.raises(CliError) as caught:
        require_confirmation(False, action="email.send")

    assert caught.value.code == "CONFIRMATION_REQUIRED"
    assert caught.value.details == {"action": "email.send", "required_flag": "--confirm"}


def test_save_file_attachments_uses_exclusive_private_files(tmp_path):
    destination = tmp_path / "downloads"

    paths = save_file_attachments(
        destination,
        [FileAttachment(name="report.txt", content=b"private")],
    )

    assert paths == [destination / "report.txt"]
    assert paths[0].read_bytes() == b"private"
    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600


def test_save_file_attachments_rejects_traversal_before_writing(tmp_path):
    destination = tmp_path / "downloads"
    attachments = [
        FileAttachment(name="safe.txt", content=b"safe"),
        FileAttachment(name="../escape.txt", content=b"unsafe"),
    ]

    with pytest.raises(CliError) as caught:
        save_file_attachments(destination, attachments)

    assert caught.value.code == "INVALID_ATTACHMENT_NAME"
    assert not destination.exists()
    assert not (tmp_path / "escape.txt").exists()


def test_save_file_attachments_rejects_duplicates_before_writing(tmp_path):
    destination = tmp_path / "downloads"
    attachments = [
        FileAttachment(name="Report.txt", content=b"first"),
        FileAttachment(name="report.txt", content=b"second"),
    ]

    with pytest.raises(CliError) as caught:
        save_file_attachments(destination, attachments)

    assert caught.value.code == "DUPLICATE_ATTACHMENT_NAME"
    assert not destination.exists()


def test_save_file_attachments_never_overwrites(tmp_path):
    destination = tmp_path / "downloads"
    destination.mkdir()
    target = destination / "report.txt"
    target.write_bytes(b"existing")

    with pytest.raises(CliError) as caught:
        save_file_attachments(
            destination,
            [FileAttachment(name="report.txt", content=b"replacement")],
        )

    assert caught.value.code == "ATTACHMENT_EXISTS"
    assert target.read_bytes() == b"existing"
