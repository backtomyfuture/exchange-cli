"""Serialize exchangelib objects to plain dictionaries."""

from .content_cleaner import html_to_markdown


def _safe_str(value):
    if value is None:
        return None
    return str(value)


def _safe_isoformat(value):
    if value is None:
        return None
    return value.isoformat()


def serialize_oof_settings(settings):
    """Return the mailbox automatic-reply configuration in JSON-safe form."""
    return {
        "state": _safe_str(getattr(settings, "state", None)),
        "external_audience": _safe_str(getattr(settings, "external_audience", None)),
        "start": _safe_isoformat(getattr(settings, "start", None)),
        "end": _safe_isoformat(getattr(settings, "end", None)),
        "internal_reply": _safe_str(getattr(settings, "internal_reply", None)),
        "external_reply": _safe_str(getattr(settings, "external_reply", None)),
    }


def serialize_mail_tip(mail_tip):
    """Return an EWS MailTips result in a stable, JSON-safe shape."""
    out_of_office = getattr(mail_tip, "out_of_office", None)
    return {
        "recipient": serialize_mailbox(getattr(mail_tip, "recipient_address", None)),
        "pending_mail_tips": _safe_str(getattr(mail_tip, "pending_mail_tips", None)),
        "out_of_office": (
            {
                "reply_body": _safe_str(getattr(out_of_office, "reply_body", None)),
                "start": _safe_isoformat(getattr(out_of_office, "start", None)),
                "end": _safe_isoformat(getattr(out_of_office, "end", None)),
            }
            if out_of_office is not None
            else None
        ),
        "mailbox_full": getattr(mail_tip, "mailbox_full", None),
        "custom_mail_tip": _safe_str(getattr(mail_tip, "custom_mail_tip", None)),
        "total_member_count": getattr(mail_tip, "total_member_count", None),
        "external_member_count": getattr(mail_tip, "external_member_count", None),
        "max_message_size": getattr(mail_tip, "max_message_size", None),
        "delivery_restricted": getattr(mail_tip, "delivery_restricted", None),
        "is_moderated": getattr(mail_tip, "is_moderated", None),
        "invalid_recipient": getattr(mail_tip, "invalid_recipient", None),
    }


def serialize_delegate(delegate):
    """Return an EWS delegate and its mailbox permission levels."""
    user_id = getattr(delegate, "user_id", None)
    permissions = getattr(delegate, "delegate_permissions", None)
    return {
        "user": {
            "sid": _safe_str(getattr(user_id, "sid", None)),
            "primary_smtp_address": _safe_str(getattr(user_id, "primary_smtp_address", None)),
            "display_name": _safe_str(getattr(user_id, "display_name", None)),
            "distinguished_user": _safe_str(getattr(user_id, "distinguished_user", None)),
            "external_user_identity": _safe_str(getattr(user_id, "external_user_identity", None)),
        },
        "permissions": {
            field: _safe_str(getattr(permissions, field, None))
            for field in (
                "calendar_folder_permission_level",
                "tasks_folder_permission_level",
                "inbox_folder_permission_level",
                "contacts_folder_permission_level",
                "notes_folder_permission_level",
                "journal_folder_permission_level",
            )
        },
        "receive_copies_of_meeting_messages": bool(
            getattr(delegate, "receive_copies_of_meeting_messages", False)
        ),
        "view_private_items": bool(getattr(delegate, "view_private_items", False)),
    }


_RULE_ADDRESS_FIELDS = {
    "from_addresses",
    "sent_to_addresses",
    "forward_as_attachment_to_recipients",
    "forward_to_recipients",
    "redirect_to_recipients",
    "send_sms_alert_to_recipients",
}


def _serialize_rule_item_id(value):
    if value is None:
        return None
    result = {"id": _safe_str(getattr(value, "id", None))}
    changekey = _safe_str(getattr(value, "changekey", None))
    if changekey is not None:
        result["changekey"] = changekey
    return result


def _serialize_rule_folder_action(value):
    if value is None:
        return None
    folder_id = getattr(value, "folder_id", None)
    if folder_id is not None:
        return _serialize_rule_item_id(folder_id)
    distinguished_folder_id = getattr(value, "distinguished_folder_id", None)
    if distinguished_folder_id is not None:
        return {"distinguished_id": _safe_str(getattr(distinguished_folder_id, "id", None))}
    return None


def _serialize_rule_component(component):
    if component is None:
        return None
    result = {}
    for field in component.FIELDS:
        value = getattr(component, field.name, None)
        if value is None:
            continue
        if field.name in _RULE_ADDRESS_FIELDS:
            result[field.name] = [getattr(mailbox, "email_address", str(mailbox)) for mailbox in value]
        elif field.name == "within_date_range":
            result[field.name] = {
                "start_date_time": _safe_isoformat(getattr(value, "start_date_time", None)),
                "end_date_time": _safe_isoformat(getattr(value, "end_date_time", None)),
            }
        elif field.name == "within_size_range":
            result[field.name] = {
                "minimum_size": getattr(value, "minimum_size", None),
                "maximum_size": getattr(value, "maximum_size", None),
            }
        elif field.name in {"copy_to_folder", "move_to_folder"}:
            result[field.name] = _serialize_rule_folder_action(value)
        elif field.name == "server_reply_with_message":
            result[field.name] = _serialize_rule_item_id(value)
        elif isinstance(value, (list, tuple)):
            result[field.name] = list(value)
        else:
            result[field.name] = _safe_str(value) if not isinstance(value, (str, int, float, bool)) else value
    return result


def serialize_rule(rule):
    """Return an inbox rule with a reusable declarative ``spec`` payload."""
    spec = {
        "display_name": _safe_str(getattr(rule, "display_name", None)),
        "priority": getattr(rule, "priority", None),
    }
    is_enabled = getattr(rule, "is_enabled", None)
    if is_enabled is not None:
        spec["is_enabled"] = is_enabled
    for field in ("conditions", "exceptions", "actions"):
        value = _serialize_rule_component(getattr(rule, field, None))
        if value is not None:
            spec[field] = value
    return {
        "id": _safe_str(getattr(rule, "id", None)),
        "spec": spec,
        "status": {
            "is_not_supported": getattr(rule, "is_not_supported", None),
            "is_in_error": getattr(rule, "is_in_error", None),
        },
    }


def _serialize_conversation_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _safe_str(getattr(value, "id", None))


def _serialize_item_id(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _safe_str(getattr(value, "id", None))


def _serialize_headers(headers):
    if not headers:
        return {}
    try:
        return {str(name): _safe_str(value) or "" for name, value in headers.items()}
    except AttributeError:
        return {"raw": _safe_str(headers) or ""}


def serialize_mailbox(mailbox):
    if mailbox is None:
        return None
    return {"name": mailbox.name or "", "email": mailbox.email_address or ""}


def _serialize_mailbox_list(mailboxes):
    if not mailboxes:
        return []
    return [serialize_mailbox(mailbox) for mailbox in mailboxes]


def serialize_attachment_summary(attachment):
    attachment_id = getattr(attachment, "attachment_id", None)
    return {
        "id": _serialize_item_id(attachment_id),
        "name": getattr(attachment, "name", None),
        "size": getattr(attachment, "size", None),
        "content_type": getattr(attachment, "content_type", None),
        "is_inline": bool(getattr(attachment, "is_inline", False)),
        "content_id": getattr(attachment, "content_id", None),
        "type": type(attachment).__name__,
    }


def serialize_email_summary(message, include_body_preview: bool = True):
    sender = getattr(message, "sender", None)
    to_recipients = getattr(message, "to_recipients", None)
    cc_recipients = getattr(message, "cc_recipients", None)
    text_body = getattr(message, "text_body", None)
    body_preview = _safe_str(text_body)[:200] if include_body_preview and text_body else ""
    return {
        "id": getattr(message, "id", None),
        "changekey": getattr(message, "changekey", None),
        "subject": getattr(message, "subject", "") or "",
        "sender": serialize_mailbox(sender),
        "to": _serialize_mailbox_list(to_recipients),
        "cc": _serialize_mailbox_list(cc_recipients),
        "datetime_received": _safe_isoformat(getattr(message, "datetime_received", None)),
        "datetime_sent": _safe_isoformat(getattr(message, "datetime_sent", None)),
        "is_read": bool(getattr(message, "is_read", False)),
        "has_attachments": bool(getattr(message, "has_attachments", False)),
        "importance": _safe_str(getattr(message, "importance", None)),
        "body_preview": body_preview,
    }


def serialize_email_detail(
    message,
    body_format="markdown",
    fields: list[str] | None = None,
    include_html: bool = False,
    max_body_length: int | None = None,
):
    result = serialize_email_summary(message)
    need_bodies = fields is None or any(
        field in fields
        for field in (
            "body",
            "body_html",
            "unique_body_html",
            "body_format",
            "body_length",
            "body_truncated",
        )
    )
    if need_bodies:
        raw_body = _safe_str(getattr(message, "body", None))
        if body_format == "markdown" and raw_body:
            body_content = html_to_markdown(raw_body)
        else:
            body_content = raw_body or ""

        body_len = len(body_content) if body_content else 0
        truncated = False
        if max_body_length is not None and max_body_length > 0 and body_len > max_body_length:
            body_content = body_content[:max_body_length]
            truncated = True

        result["body"] = body_content
        result["body_format"] = body_format
        result["body_length"] = body_len
        result["body_truncated"] = truncated

        want_html = include_html or (fields is not None and any(f in fields for f in ("body_html", "unique_body_html")))
        if want_html:
            result["body_html"] = raw_body
            result["unique_body_html"] = _safe_str(getattr(message, "unique_body", None))

    result["conversation_id"] = _serialize_conversation_id(getattr(message, "conversation_id", None))
    result["internet_message_id"] = _safe_str(getattr(message, "message_id", None))
    result["parent_folder_id"] = _serialize_item_id(getattr(message, "parent_folder_id", None))
    result["item_class"] = _safe_str(getattr(message, "item_class", None))
    result["size"] = getattr(message, "size", None)
    result["categories"] = list(getattr(message, "categories", None) or [])
    result["sensitivity"] = _safe_str(getattr(message, "sensitivity", None))
    result["is_draft"] = bool(getattr(message, "is_draft", False))
    result["datetime_created"] = _safe_isoformat(getattr(message, "datetime_created", None))
    result["last_modified_time"] = _safe_isoformat(getattr(message, "last_modified_time", None))
    result["in_reply_to"] = _safe_str(getattr(message, "in_reply_to", None))
    result["references"] = _safe_str(getattr(message, "references", None))
    result["reply_to"] = _serialize_mailbox_list(getattr(message, "reply_to", None))
    result["headers"] = _serialize_headers(getattr(message, "headers", None))
    result["bcc"] = _serialize_mailbox_list(getattr(message, "bcc_recipients", None))
    result["attachments"] = [serialize_attachment_summary(att) for att in (getattr(message, "attachments", None) or [])]
    if fields is None:
        return result
    return {field: result[field] for field in fields if field in result}


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


def serialize_folder(folder, path: str | None = None):
    data = {
        "id": getattr(folder, "id", None),
        "name": getattr(folder, "name", "") or "",
        "total_count": getattr(folder, "total_count", 0),
        "unread_count": getattr(folder, "unread_count", 0),
        "child_folder_count": getattr(folder, "child_folder_count", 0),
    }
    if path is not None:
        data["path"] = path
    return data


def serialize_resolved_name(mailbox, contact=None):
    payload = serialize_mailbox(mailbox) or {"name": "", "email": ""}
    payload["mailbox_type"] = _safe_str(getattr(mailbox, "mailbox_type", None)) if mailbox else None
    if contact is None:
        payload["display_name"] = payload["name"]
        payload["source"] = "directory"
        return payload
    payload["display_name"] = getattr(contact, "display_name", None) or payload["name"]
    payload["job_title"] = getattr(contact, "job_title", None) or ""
    payload["department"] = getattr(contact, "department", None) or ""
    payload["company"] = getattr(contact, "company_name", None) or ""
    payload["source"] = "directory"
    return payload
