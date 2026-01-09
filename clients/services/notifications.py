"""Email notification helpers for client lifecycle events."""
from __future__ import annotations

import logging
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


def _get_pdf_font_path() -> Path | None:
    configured_path = getattr(settings, "PDF_FONT_PATH", "")
    if configured_path:
        path = Path(configured_path)
        if path.exists():
            return path
    candidate_paths = [
        Path(settings.BASE_DIR) / "static" / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    for path in candidate_paths:
        if path.exists():
            return path
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
    font = ImageFont.truetype(str(font_path), 24) if font_path else ImageFont.load_default()
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

    language = _get_preferred_language(client)
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
