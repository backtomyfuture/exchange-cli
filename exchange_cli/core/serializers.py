"""Serialize exchangelib objects to plain dictionaries."""


def _safe_str(value):
    if value is None:
        return None
    return str(value)


def _safe_isoformat(value):
    if value is None:
        return None
    return value.isoformat()


def serialize_mailbox(mailbox):
    if mailbox is None:
        return None
    return {"name": mailbox.name or "", "email": mailbox.email_address or ""}


def _serialize_mailbox_list(mailboxes):
    if not mailboxes:
        return []
    return [serialize_mailbox(mailbox) for mailbox in mailboxes]


def serialize_attachment_summary(attachment):
    return {
        "name": getattr(attachment, "name", None),
        "size": getattr(attachment, "size", None),
        "content_type": getattr(attachment, "content_type", None),
    }


def serialize_email_summary(message, include_body_preview: bool = True):
    body_preview = _safe_str(message.text_body)[:200] if include_body_preview and message.text_body else ""
    return {
        "id": message.id,
        "subject": message.subject or "",
        "sender": serialize_mailbox(message.sender),
        "to": _serialize_mailbox_list(message.to_recipients),
        "cc": _serialize_mailbox_list(message.cc_recipients),
        "datetime_received": _safe_isoformat(message.datetime_received),
        "datetime_sent": _safe_isoformat(message.datetime_sent),
        "is_read": bool(message.is_read),
        "has_attachments": bool(message.has_attachments),
        "importance": _safe_str(message.importance),
        "body_preview": body_preview,
    }


def serialize_email_detail(message):
    result = serialize_email_summary(message)
    result["body"] = _safe_str(message.body)
    result["bcc"] = _serialize_mailbox_list(message.bcc_recipients)
    result["attachments"] = [serialize_attachment_summary(att) for att in (message.attachments or [])]
    return result


def _serialize_attendee(attendee):
    mailbox = getattr(attendee, "mailbox", None)
    return {
        "name": mailbox.name if mailbox else "",
        "email": mailbox.email_address if mailbox else "",
        "response": _safe_str(getattr(attendee, "response_type", None)),
    }


def serialize_calendar_event(event):
    attendees = []
    for attendee in event.required_attendees or []:
        attendees.append(_serialize_attendee(attendee))
    for attendee in event.optional_attendees or []:
        attendees.append(_serialize_attendee(attendee))

    return {
        "id": event.id,
        "subject": event.subject or "",
        "start": _safe_isoformat(event.start),
        "end": _safe_isoformat(event.end),
        "location": _safe_str(event.location),
        "organizer": serialize_mailbox(event.organizer),
        "attendees": attendees,
        "is_all_day": bool(event.is_all_day),
        "body_preview": _safe_str(event.text_body)[:200] if event.text_body else "",
    }


def serialize_task(task):
    return {
        "id": task.id,
        "subject": task.subject or "",
        "status": _safe_str(task.status),
        "due_date": _safe_isoformat(task.due_date),
        "start_date": _safe_isoformat(task.start_date),
        "complete_date": _safe_isoformat(task.complete_date),
        "percent_complete": task.percent_complete,
        "importance": _safe_str(task.importance),
        "body_preview": _safe_str(task.text_body)[:200] if task.text_body else "",
    }


def serialize_contact(contact):
    emails = []
    for email in contact.email_addresses or []:
        emails.append({"email": email.email, "label": _safe_str(email.label)})

    phones = []
    for phone in contact.phone_numbers or []:
        phones.append({"number": phone.phone_number, "label": _safe_str(phone.label)})

    return {
        "id": contact.id,
        "display_name": contact.display_name or "",
        "given_name": contact.given_name or "",
        "surname": contact.surname or "",
        "emails": emails,
        "phones": phones,
        "company": contact.company_name or "",
        "department": contact.department or "",
        "job_title": contact.job_title or "",
    }


def serialize_folder(folder):
    return {
        "id": getattr(folder, "id", None),
        "name": folder.name or "",
        "total_count": getattr(folder, "total_count", 0),
        "unread_count": getattr(folder, "unread_count", 0),
        "child_folder_count": getattr(folder, "child_folder_count", 0),
    }
