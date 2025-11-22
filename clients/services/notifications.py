"""Email notification helpers for client lifecycle events."""
from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import Client

logger = logging.getLogger(__name__)


def _send_email(subject: str, body: str, recipients: Iterable[str]) -> int:
    try:
        return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, list(recipients))
    except Exception:  # pragma: no cover - defensive safeguard
        logger.exception("Failed to send notification email")
        return 0


def send_required_documents_email(client: Client) -> int:
    """Send the required document checklist to the client upon account creation."""
    if not client.email:
        return 0

    checklist = client.get_document_checklist()
    if not checklist:
        return 0

    context = {
        "client": client,
        "documents": [item.get("name") for item in checklist],
    }
    subject = _("Список необходимых документов")
    body = render_to_string("clients/email/required_documents.txt", context)
    return _send_email(subject, body, [client.email])


def send_expired_documents_email(client: Client) -> int:
    """Send a summary of expired documents after fingerprints are submitted."""
    if not client.email:
        return 0

    today = timezone.localdate()
    expired_documents = client.documents.filter(expiry_date__isnull=False, expiry_date__lte=today).order_by(
        "expiry_date"
    )

    context = {
        "client": client,
        "fingerprints_date": client.fingerprints_date,
        "expired_documents": expired_documents,
        "today": today,
    }
    subject = _("Истекшие документы после сдачи отпечатков")
    body = render_to_string("clients/email/expired_documents.txt", context)
    return _send_email(subject, body, [client.email])
