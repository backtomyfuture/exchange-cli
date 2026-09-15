from datetime import datetime, timezone
from unittest.mock import MagicMock

from exchange_cli.core.serializers import (
    serialize_calendar_event,
    serialize_contact,
    serialize_email_detail,
    serialize_email_summary,
    serialize_folder,
    serialize_mailbox,
    serialize_resolved_name,
    serialize_task,
)


def _mock_mailbox(name="Test", email="test@x.com"):
    mailbox = MagicMock()
    mailbox.name = name
    mailbox.email_address = email
    return mailbox


def _mock_message(**kwargs):
    msg = MagicMock()
    msg.id = kwargs.get("id", "AAMk123")
    msg.changekey = kwargs.get("changekey", "CK1")
    msg.subject = kwargs.get("subject", "Test Subject")
    msg.sender = _mock_mailbox("Sender", "sender@x.com")
    msg.to_recipients = [_mock_mailbox("To1", "to1@x.com")]
    msg.cc_recipients = []
    msg.bcc_recipients = []
    msg.datetime_received = kwargs.get("datetime_received", datetime(2024, 7, 15, 10, 30, tzinfo=timezone.utc))
    msg.datetime_sent = kwargs.get("datetime_sent", datetime(2024, 7, 15, 10, 29, tzinfo=timezone.utc))
    msg.is_read = kwargs.get("is_read", True)
    msg.has_attachments = kwargs.get("has_attachments", False)
    msg.importance = kwargs.get("importance", "Normal")
    msg.text_body = kwargs.get("text_body", "Preview text")
    msg.body = kwargs.get("body", "<p>Full body</p>")
    msg.attachments = kwargs.get("attachments", [])
    return msg


class TestSerializeMailbox:
    def test_basic(self):
        mailbox = _mock_mailbox("John", "john@x.com")
        assert serialize_mailbox(mailbox) == {"name": "John", "email": "john@x.com"}

    def test_none(self):
        assert serialize_mailbox(None) is None


class TestSerializeEmailSummary:
    def test_basic(self):
        msg = _mock_message()
        result = serialize_email_summary(msg)
        assert result["id"] == "AAMk123"
        assert result["subject"] == "Test Subject"
        assert result["sender"]["email"] == "sender@x.com"
        assert result["is_read"] is True
        assert "body" not in result

    def test_with_attachments(self):
        msg = _mock_message(has_attachments=True)
        result = serialize_email_summary(msg)
        assert result["has_attachments"] is True

    def test_without_preview(self):
        msg = _mock_message(text_body="Should not appear")
        result = serialize_email_summary(msg, include_body_preview=False)
        assert result["body_preview"] == ""


class TestSerializeEmailDetail:
    def test_includes_body(self):
        msg = _mock_message()
        result = serialize_email_detail(msg)
        assert "body" in result

    def test_default_converts_body_to_markdown(self):
        msg = _mock_message(body="<html><body><p>Hello <b>World</b></p></body></html>")
        result = serialize_email_detail(msg)
        assert "<html>" not in result["body"]
        assert "<p>" not in result["body"]
        assert "Hello" in result["body"]
        assert "World" in result["body"]
        assert result["body_format"] == "markdown"

    def test_html_format_preserves_raw_body(self):
        msg = _mock_message(body="<p>Full body</p>")
        result = serialize_email_detail(msg, body_format="html")
        assert result["body"] == "<p>Full body</p>"
        assert result["body_format"] == "html"

    def test_plain_text_body_passthrough(self):
        msg = _mock_message(body="Just plain text")
        result = serialize_email_detail(msg)
        assert result["body"] == "Just plain text"
        assert result["body_format"] == "markdown"
        assert "body_html" not in result

    def test_include_html_includes_raw_bodies(self):
        msg = _mock_message(body="<p>Hello</p>")
        msg.unique_body = "<p>Unique</p>"
        result = serialize_email_detail(msg, include_html=True)
        assert result["body_html"] == "<p>Hello</p>"
        assert result["unique_body_html"] == "<p>Unique</p>"

    def test_max_body_length_truncation(self):
        msg = _mock_message(body="1234567890")
        result = serialize_email_detail(msg, max_body_length=5)
        assert result["body"] == "12345"
        assert result["body_truncated"] is True
        assert result["body_length"] == 10


class TestSerializeCalendarEvent:
    def test_basic(self):
        event = MagicMock()
        event.id = "EVT1"
        event.changekey = "CK1"
        event.subject = "Meeting"
        event.start = datetime(2024, 7, 15, 10, 0, tzinfo=timezone.utc)
        event.end = datetime(2024, 7, 15, 11, 0, tzinfo=timezone.utc)
        event.location = "Room A"
        event.organizer = _mock_mailbox("Boss", "boss@x.com")
        event.required_attendees = [MagicMock(mailbox=_mock_mailbox("John", "john@x.com"), response_type="Accept")]
        event.optional_attendees = []
        event.is_all_day = False
        event.text_body = "Agenda"
        result = serialize_calendar_event(event)
        assert result["subject"] == "Meeting"
        assert result["location"] == "Room A"
        assert len(result["attendees"]) == 1


class TestSerializeTask:
    def test_basic(self):
        task = MagicMock()
        task.id = "T1"
        task.changekey = "CK1"
        task.subject = "Review PR"
        task.status = "NotStarted"
        task.due_date = MagicMock()
        task.due_date.isoformat.return_value = "2024-07-20"
        task.start_date = None
        task.complete_date = None
        task.percent_complete = 0
        task.importance = "Normal"
        task.text_body = "Details"
        result = serialize_task(task)
        assert result["subject"] == "Review PR"
        assert result["status"] == "NotStarted"


class TestSerializeContact:
    def test_basic(self):
        contact = MagicMock()
        contact.id = "C1"
        contact.changekey = "CK1"
        contact.display_name = "John Doe"
        contact.given_name = "John"
        contact.surname = "Doe"
        contact.email_addresses = [MagicMock(email="john@x.com", label="EmailAddress1")]
        contact.company_name = "Acme"
        contact.department = "Engineering"
        contact.job_title = "Engineer"
        contact.phone_numbers = [MagicMock(phone_number="+1234", label="BusinessPhone")]
        result = serialize_contact(contact)
        assert result["display_name"] == "John Doe"
        assert len(result["emails"]) == 1


class TestSerializeResolvedName:
    def test_includes_directory_source(self):
        mailbox = _mock_mailbox("Zhang San", "zhang.san@example.com")
        mailbox.mailbox_type = "Mailbox"
        contact = MagicMock(display_name="Zhang San", job_title="Engineer", department="IT", company_name="Acme")
        result = serialize_resolved_name(mailbox, contact)
        assert result["email"] == "zhang.san@example.com"
        assert result["source"] == "directory"
        assert result["job_title"] == "Engineer"


class TestSerializeFolder:
    def test_basic(self):
        folder = MagicMock()
        folder.id = "F1"
        folder.name = "Inbox"
        folder.total_count = 150
        folder.unread_count = 5
        folder.child_folder_count = 2
        result = serialize_folder(folder)
        assert result["name"] == "Inbox"
        assert result["unread_count"] == 5


class TestSerializeAttachmentSummary:
    def test_attachment_summary(self):
        from exchange_cli.core.serializers import serialize_attachment_summary

        att = MagicMock()
        att.name = "image.png"
        att.size = 1024
        att.content_type = "image/png"
        att.is_inline = True
        att.content_id = "logo@corp"

        data = serialize_attachment_summary(att)
        assert data["name"] == "image.png"
        assert data["size"] == 1024
        assert data["content_type"] == "image/png"
        assert data["is_inline"] is True
        assert data["content_id"] == "logo@corp"
