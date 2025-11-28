"""Email notification helpers for client lifecycle events."""
from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import select_template
from django.utils import timezone
from django.utils.translation import override

from clients.models import Client, Document

logger = logging.getLogger(__name__)

EMAIL_SUBJECTS: dict[str, dict[str, str]] = {
    "required_documents": {
        "default": "Список необходимых документов",
        "en": "Required documents checklist",
        "pl": "Lista wymaganych dokumentów",
        "ru": "Список необходимых документов",
    },
    "expired_documents": {
        "default": "Истекшие документы после сдачи отпечатков",
        "en": "Expired documents after fingerprints",
        "pl": "Wygasłe dokumenty po złożeniu odcisków",
        "ru": "Истекшие документы после сдачи отпечатков",
    },
    "missing_documents": {
        "default": "Список недостающих документов",
        "en": "Missing documents checklist",
        "pl": "Brakujące dokumenty w checkliście",
        "ru": "Список недостающих документов",
    },
    "expiring_documents": {
        "default": "Документы скоро истекают",
        "en": "Documents expiring soon",
        "pl": "Dokumenty wkrótce tracą ważność",
        "ru": "Документы скоро истекают",
    },
}


def _get_preferred_language(client: Client) -> str:
    return (client.language or settings.LANGUAGE_CODE or "ru")[:2]


def _get_subject(key: str, language: str) -> str:
    subjects = EMAIL_SUBJECTS.get(key, {})
    return subjects.get(language) or subjects.get("default") or ""


def _render_email_body(template_key: str, context: dict, language: str) -> str:
    template_names = [
        f"clients/email/{language}/{template_key}.txt",
        f"clients/email/{template_key}.txt",
    ]
    template = select_template(template_names)
    with override(language):
        return template.render(context)


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

    checklist = client.get_document_checklist() or []
    if not checklist:
        return 0

    context = {
        "client": client,
        "documents": [item.get("name") for item in checklist],
    }
    subject = _get_subject("required_documents", language)
    body = _render_email_body("required_documents", context, language)
    return _send_email(subject, body, [client.email])


def send_expired_documents_email(client: Client) -> int:
    """Send a summary of expired documents after fingerprints are submitted."""
    if not client.email:
        return 0

    language = _get_preferred_language(client)
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
    with override(language):
        subject = _get_subject("expired_documents", language)
    body = _render_email_body("expired_documents", context, language)
    return _send_email(subject, body, [client.email])


def send_missing_documents_email(client: Client) -> int:
    """Send a reminder listing documents that are still missing for the client."""

    if not client.email:
        return 0

    language = _get_preferred_language(client)
    checklist = client.get_document_checklist()
    missing = []
    uploaded_with_expiry = []

    for item in checklist:
        if item.get("is_uploaded"):
            latest_document = (item.get("documents") or [None])[0]
            expiry_date = getattr(latest_document, "expiry_date", None)
            if expiry_date:
                uploaded_with_expiry.append(
                    {
                        "name": item.get("name"),
                        "expiry_date": expiry_date,
                    }
                )
            continue

        latest_document = (item.get("documents") or [None])[0]
        missing.append(
            {
                "name": item.get("name"),
                "expiry_date": getattr(latest_document, "expiry_date", None),
            }
        )

    if not missing:
        return 0

    context = {
        "client": client,
        "documents": missing,
        "uploaded_with_expiry": uploaded_with_expiry,
    }
    subject = _get_subject("missing_documents", language)
    body = _render_email_body("missing_documents", context, language)
    return _send_email(subject, body, [client.email])


def send_expiring_documents_email(client: Client, documents: list[Document]) -> int:
    """Send a notice about documents expiring soon (within the next week)."""

    if not client.email or not documents:
        return 0

    checklist = client.get_document_checklist()
    missing_documents = []

    for item in checklist:
        if item.get("is_uploaded"):
            continue

        latest_document = (item.get("documents") or [None])[0]
        missing_documents.append(
            {
                "name": item.get("name"),
                "expiry_date": getattr(latest_document, "expiry_date", None),
            }
        )

    context = {
        "client": client,
        "documents": sorted(documents, key=lambda doc: doc.expiry_date or timezone.localdate()),
        "missing_documents": missing_documents,
    }
    subject = _get_subject("expiring_documents", language)
    body = _render_email_body("expiring_documents", context, language)
    return _send_email(subject, body, [client.email])
