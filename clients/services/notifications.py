"""Email notification helpers for client lifecycle events."""
from __future__ import annotations

import logging
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.template.loader import select_template
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import override
from PIL import Image, ImageDraw, ImageFont

from clients.models import Client, Document

logger = logging.getLogger(__name__)

EMAIL_SUBJECTS: dict[str, str] = {
    "required_documents": _("Список необходимых документов"),
    "expired_documents": _("Истекшие документы после сдачи отпечатков"),
    "missing_documents": _("Список недостающих документов"),
    "expiring_documents": _("Документы скоро истекают"),
    "appointment_notification": _("Уведомление о встрече"),
}


def _get_preferred_language(client: Client) -> str:
    return (client.language or settings.LANGUAGE_CODE or "ru")[:2]


def _get_subject(key: str, language: str) -> str:
    subject = EMAIL_SUBJECTS.get(key, "")
    if not subject:
        return ""

    with override(language):
        return str(subject)


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
        recipient_list = list(recipients)
        sent_count = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipient_list)
        if sent_count:
            _send_confirmation_email(subject, body, recipient_list)
        return sent_count
    except Exception:  # pragma: no cover - defensive safeguard
        logger.exception("Failed to send notification email")
        return 0


def _get_staff_recipients() -> list[str]:
    reply_to = getattr(settings, "EMAIL_REPLY_TO", "")
    default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    recipients = [email for email in (reply_to, default_from) if email]
    return list(dict.fromkeys(recipients))


PDF_FONT_TEST_TEXT = "Привет"


def _get_pdf_font_path() -> Path | None:
    configured_path = getattr(settings, "PDF_FONT_PATH", "")
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return path
        logger.warning("PDF font path does not exist: %s", configured_path)
    nix_store = Path("/nix/store")
    nix_candidates: list[Path] = []
    if nix_store.exists():
        nix_candidates.extend(
            nix_store.glob("**/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
        nix_candidates.extend(
            nix_store.glob("**/share/fonts/truetype/noto/NotoSans-Regular.ttf")
        )
    candidate_paths = [
        Path(settings.BASE_DIR) / "static" / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        *nix_candidates,
    ]
    for path in candidate_paths:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), 24)
            except OSError:
                continue
            mask = font.getmask(PDF_FONT_TEST_TEXT)
            if not mask or mask.getbbox() is None:
                continue
            return path
    logger.warning("PDF font not found in default locations; falling back to PIL default font.")
    return None


def _wrap_text_lines(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _render_email_pdf(text: str) -> bytes:
    page_width, page_height = (1240, 1754)
    margin = 80
    font_path = _get_pdf_font_path()
    if font_path:
        font = ImageFont.truetype(str(font_path), 24)
    else:
        logger.warning("Using PIL default font for PDF rendering.")
        font = ImageFont.load_default()
    temp_image = Image.new("RGB", (1, 1), "white")
    draw = ImageDraw.Draw(temp_image)
    max_width = page_width - (margin * 2)
    lines = _wrap_text_lines(text, draw, font, max_width)
    line_height = font.getbbox("Hg")[3] - font.getbbox("Hg")[1] + 6
    max_lines_per_page = max(1, (page_height - (margin * 2)) // line_height)

    pages: list[Image.Image] = []
    for start in range(0, len(lines), max_lines_per_page):
        page = Image.new("RGB", (page_width, page_height), "white")
        page_draw = ImageDraw.Draw(page)
        y = margin
        for line in lines[start:start + max_lines_per_page]:
            page_draw.text((margin, y), line, font=font, fill="black")
            y += line_height
        pages.append(page)

    buffer = BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()


def _send_confirmation_email(subject: str, body: str, recipients: list[str]) -> None:
    staff_recipients = _get_staff_recipients()
    if not staff_recipients:
        return

    timestamp = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    recipient_list = ", ".join(recipients)
    pdf_text = "\n".join(
        [
            _("Подтверждение отправки письма клиенту."),
            _("Время отправки: %(timestamp)s") % {"timestamp": timestamp},
            _("Кому: %(recipients)s") % {"recipients": recipient_list},
            _("Тема: %(subject)s") % {"subject": subject},
            "",
            _("Текст письма:"),
            body,
        ]
    )
    pdf_bytes = _render_email_pdf(pdf_text)
    confirmation_subject = _("Подтверждение отправки письма клиенту")
    confirmation_body = _(
        "Письмо клиенту было отправлено. Во вложении находится текст отправленного письма."
    )
    try:
        message = EmailMessage(
            confirmation_subject,
            confirmation_body,
            settings.DEFAULT_FROM_EMAIL,
            staff_recipients,
        )
        message.attach("sent-email.pdf", pdf_bytes, "application/pdf")
        message.send()
    except Exception:  # pragma: no cover - defensive safeguard
        logger.exception("Failed to send confirmation email")


def send_required_documents_email(client: Client) -> int:
    """Send the required document checklist to the client upon account creation."""
    if not client.email:
        return 0

    language = _get_preferred_language(client)
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
    # Only check documents explicitly registered in the database.
    # If there are no DB records for the purpose, fall back to the global checklist.
    from clients.models import DocumentRequirement
    has_db_records = DocumentRequirement.objects.filter(
        application_purpose=client.application_purpose
    ).exists()
    catalog = DocumentRequirement.catalog_for(
        client.application_purpose,
        language,
        include_optional=False,
        include_fallback=not has_db_records,
    )
    uploaded_codes = set(
        client.documents.values_list("document_type", flat=True)
    )
    missing = []
    uploaded_with_expiry = []

    for item in catalog:
        code = item["code"]
        if code in uploaded_codes:
            # Document is uploaded — check for expiry info
            doc = client.documents.filter(document_type=code).order_by("-uploaded_at").first()
            expiry_date = getattr(doc, "expiry_date", None)
            if expiry_date:
                uploaded_with_expiry.append(
                    {
                        "name": item.get("label"),
                        "expiry_date": expiry_date,
                    }
                )
            continue

        missing.append(
            {
                "name": item.get("label"),
                "expiry_date": None,
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

    language = _get_preferred_language(client)
    today = timezone.localdate()
    cutoff = today + timedelta(days=7)
    all_documents = (
        client.documents.filter(expiry_date__isnull=False)
        .order_by("expiry_date")
    )
    expired_documents = [
        document for document in all_documents if document.expiry_date and document.expiry_date < today
    ]
    expiring_soon_documents = [
        document
        for document in all_documents
        if document.expiry_date and today <= document.expiry_date <= cutoff
    ]
    valid_documents = [
        document for document in all_documents if document.expiry_date and document.expiry_date > cutoff
    ]
    checklist = client.get_document_checklist() or []
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

    today = timezone.localdate()
    soon_days = 3
    soon_cutoff = today + timedelta(days=soon_days)
    expired_documents = []
    expiring_documents = []
    for document in sorted(documents, key=lambda doc: doc.expiry_date or today):
        if not document.expiry_date:
            continue
        if document.expiry_date < today:
            expired_documents.append(document)
        else:
            expiring_documents.append(document)

    expiring_soon_documents = [
        document for document in expiring_documents if document.expiry_date and document.expiry_date <= soon_cutoff
    ]
    expiring_later_documents = [
        document for document in expiring_documents if document.expiry_date and document.expiry_date > soon_cutoff
    ]

    context = {
        "client": client,
        "expired_documents": expired_documents,
        "expiring_soon_documents": expiring_soon_documents,
        "valid_documents": valid_documents,
        "missing_documents": missing_documents,
        "today": today,
        "cutoff": cutoff,
    }
    subject = _get_subject("expiring_documents", language)
    body = _render_email_body("expiring_documents", context, language)
    return _send_email(subject, body, [client.email])


def send_appointment_notification_email(client: Client) -> int:
    """Send a notification about a fingerprint appointment."""
    if not client.email or not client.fingerprints_date:
        return 0

    language = _get_preferred_language(client)
    context = {
        "client": client,
        "fingerprints_date": client.fingerprints_date,
        "fingerprints_time": client.fingerprints_time,
        "fingerprints_location": client.fingerprints_location,
    }
    subject = _get_subject("appointment_notification", language)
    body = _render_email_body("appointment_notification", context, language)
    return _send_email(subject, body, [client.email])
