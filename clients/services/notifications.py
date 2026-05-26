"""Email notification helpers for client lifecycle events."""
from __future__ import annotations

import logging
import hashlib
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING

from django.conf import settings
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.core.mail import send_mail
from django.template.loader import select_template
from django.utils import timezone
from django.utils.translation import gettext as _, gettext_lazy
from django.utils.translation import override
from PIL import Image, ImageDraw, ImageFont

from clients.constants import DocumentType
from clients.models import Client, Document
from clients.services.wniosek import get_submitted_document_codes
from clients.services.zus import format_zus_months, missing_zus_months

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)

EMAIL_SUBJECTS = {
    "required_documents": gettext_lazy("Список необходимых документов"),
    "expired_documents": gettext_lazy("Истекшие документы после сдачи отпечатков"),
    "missing_documents": gettext_lazy("Список недостающих документов"),
    "expiring_documents": gettext_lazy("Документы скоро истекают"),
    "appointment_notification": gettext_lazy("Уведомление о встрече"),
}


def build_email_idempotency_key(*parts: object) -> str:
    normalized = "|".join(str(part).strip() for part in parts if part is not None)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _get_preferred_language(client: Client) -> str:
    return str(client.language or settings.LANGUAGE_CODE or "ru")[:2]


def _get_subject(key: str, language: str) -> str:
    subject = EMAIL_SUBJECTS.get(key, "")
    if not subject:
        return ""

    with override(language):
        return str(subject)


def _render_email_body(template_key: str, context: dict[str, Any], language: str) -> str:
    template_names = [
        f"clients/email/{language}/{template_key}.txt",
        f"clients/email/{template_key}.txt",
    ]
    template = select_template(template_names)
    with override(language):
        return str(template.render(context))


def _reserve_idempotent_email_send(
    subject: str,
    body: str,
    recipients: list[str],
    *,
    client: Client | None = None,
    template_type: str = "",
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    idempotency_key: str = "",
) -> bool:
    if not idempotency_key:
        return True

    from clients.models import EmailLog

    real_sent_by = sent_by if sent_by and sent_by.is_authenticated else None

    payload: dict[str, Any] = {
        "client": client,
        "subject": subject,
        "body": body,
        "recipients": ", ".join(recipients),
        "template_type": template_type,
        "sent_by": real_sent_by,
        "delivery_status": EmailLog.DELIVERY_STATUS_QUEUED,
        "error_message": "",
    }
    blocking_statuses = {
        EmailLog.DELIVERY_STATUS_QUEUED,
        EmailLog.DELIVERY_STATUS_SENT,
    }

    try:
        with transaction.atomic():
            existing = (
                EmailLog.objects.select_for_update()
                .filter(idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None and existing.delivery_status in blocking_statuses:
                return False

            if existing is not None:
                for field_name, value in payload.items():
                    setattr(existing, field_name, value)
                existing.save(update_fields=[*payload.keys()])
                return True

            EmailLog.objects.create(
                **payload,
                idempotency_key=idempotency_key,
            )
            return True
    except IntegrityError:
        logger.info("Skipped duplicate queued email for idempotency_key=%s", idempotency_key)
        return False


def _send_email(
    subject: str,
    body: str,
    recipients: Iterable[str],
    *,
    client: Client | None = None,
    template_type: str = "",
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    idempotency_key: str = "",
) -> int:
    recipient_list = list(recipients)

    if not _reserve_idempotent_email_send(
        subject,
        body,
        recipient_list,
        client=client,
        template_type=template_type,
        sent_by=sent_by,
        idempotency_key=idempotency_key,
    ):
        return 0

    result = {"sent_count": 0}

    def _do_send() -> None:
        """Run SMTP I/O and record the final delivery status."""

        try:
            sent_count = send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipient_list)
            result["sent_count"] = sent_count
            if sent_count:
                try:
                    _send_confirmation_email(subject, body, recipient_list)
                except Exception as exc:
                    logger.warning(
                        "Failed to send staff confirmation email: error_type=%s",
                        type(exc).__name__,
                    )
                _log_email(
                    subject,
                    body,
                    recipient_list,
                    client=client,
                    template_type=template_type,
                    sent_by=sent_by,
                    idempotency_key=idempotency_key,
                    delivery_status="sent",
                )
            else:
                _log_email(
                    subject,
                    body,
                    recipient_list,
                    client=client,
                    template_type=template_type,
                    sent_by=sent_by,
                    idempotency_key=idempotency_key,
                    delivery_status="failed",
                    error_message="send returned 0",
                )
        except Exception as exc:
            logger.warning(
                "Failed to send notification email: template=%s client_id=%s error_type=%s",
                template_type,
                getattr(client, "pk", None),
                type(exc).__name__,
            )
            result["sent_count"] = 0
            _log_email(
                subject,
                body,
                recipient_list,
                client=client,
                template_type=template_type,
                sent_by=sent_by,
                idempotency_key=idempotency_key,
                delivery_status="failed",
                error_message="send failed",
            )
    _do_send()
    return result["sent_count"]


def _log_email(
    subject: str,
    body: str,
    recipients: list[str],
    *,
    client: Client | None = None,
    template_type: str = "",
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    idempotency_key: str = "",
    delivery_status: str = "sent",
    error_message: str = "",
) -> None:
    from clients.models import EmailLog
    
    real_sent_by = sent_by if sent_by and sent_by.is_authenticated else None
    
    try:
        payload = {
            "client": client,
            "subject": subject,
            "body": body,
            "recipients": ", ".join(recipients),
            "template_type": template_type,
            "sent_by": real_sent_by,
            "delivery_status": delivery_status,
            "error_message": error_message,
        }
        if idempotency_key:
            with transaction.atomic():
                EmailLog.objects.update_or_create(
                    idempotency_key=idempotency_key,
                    defaults=payload,
                )
        else:
            EmailLog.objects.create(
                **payload,
                idempotency_key="",
            )
    except IntegrityError:
        logger.info("Skipped duplicate email log for idempotency_key=%s", idempotency_key)
    except Exception as exc:
        logger.warning("Failed to log sent email: error_type=%s", type(exc).__name__)


def _get_staff_recipients() -> list[str]:
    reply_to = str(getattr(settings, "EMAIL_REPLY_TO", ""))
    default_from = str(getattr(settings, "DEFAULT_FROM_EMAIL", ""))
    recipients = [email for email in (reply_to, default_from) if email]
    return list(dict.fromkeys(recipients))


PDF_FONT_TEST_TEXT = "Привет"


def _get_pdf_font_path() -> Path | None:
    configured_path = str(getattr(settings, "PDF_FONT_PATH", ""))
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
        Path(str(settings.BASE_DIR)) / "static" / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/arialuni.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
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


def _wrap_text_lines(text: str, draw: ImageDraw.ImageDraw, font: Any, max_width: int) -> list[str]:
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
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    if font_path:
        font = ImageFont.truetype(str(font_path), 24)
    else:
        logger.warning("Using PIL default font for PDF rendering.")
        font = ImageFont.load_default()
    temp_image = Image.new("RGB", (1, 1), "white")
    draw = ImageDraw.Draw(temp_image)
    max_width = page_width - (margin * 2)
    lines = _wrap_text_lines(text, draw, font, max_width)
    
    # Calculate line height
    if hasattr(font, "getbbox"):
        bbox = font.getbbox("Hg")
        line_height = int(bbox[3] - bbox[1] + 6)
    else:
        # Fallback for old PIL versions or default font
        line_height = 30
        
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
    if pages:
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
            str(_("Подтверждение отправки письма клиенту.")),
            str(_("Время отправки: %(timestamp)s") % {"timestamp": timestamp}),
            str(_("Кому: %(recipients)s") % {"recipients": recipient_list}),
            str(_("Тема: %(subject)s") % {"subject": subject}),
            "",
            str(_("Текст письма:")),
            body,
        ]
    )
    pdf_bytes = _render_email_pdf(pdf_text)
    confirmation_subject = str(_("Подтверждение отправки письма клиенту"))
    confirmation_body = str(_(
        "Письмо клиенту было отправлено. Во вложении находится текст отправленного письма."
    ))
    try:
        from django.core.mail import EmailMultiAlternatives
        message = EmailMultiAlternatives(
            confirmation_subject,
            confirmation_body,
            settings.DEFAULT_FROM_EMAIL,
            staff_recipients,
        )
        message.attach_alternative(f"<p>{confirmation_body}</p>", "text/html")
        message.attach("sent-email.pdf", pdf_bytes, "application/pdf")
        message.send()
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logger.warning("Failed to send confirmation email: error_type=%s", type(exc).__name__)


def _get_required_documents_context(client: Client, language: str | None = None) -> dict[str, Any] | None:
    if language is None:
        language = _get_preferred_language(client)
    from clients.models import DocumentRequirement
    purpose = client.get_document_requirement_purpose()
    catalog = DocumentRequirement.catalog_for(
        purpose,
        language,
        include_optional=False,
        include_fallback=True,
    )
    if not catalog:
        return None
    return {
        "client": client,
        "documents": [item.get("label") for item in catalog],
    }


def send_required_documents_email(client: Client, *, sent_by: AbstractBaseUser | AnonymousUser | None = None) -> int:
    """Send the required document checklist to the client upon account creation."""
    if not client.email:
        return 0

    context = _get_required_documents_context(client)
    if not context:
        return 0

    language = _get_preferred_language(client)
    subject = _get_subject("required_documents", language)
    body = _render_email_body("required_documents", context, language)
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="required_documents",
        sent_by=sent_by,
        idempotency_key=build_email_idempotency_key("required_documents", client.pk, client.email),
    )


def _get_expired_documents_context(client: Client) -> dict[str, Any] | None:
    today = timezone.localdate()
    expired_documents = client.documents.filter(expiry_date__isnull=False, expiry_date__lt=today).order_by(
        "expiry_date"
    )
    if not expired_documents.exists():
        return None

    return {
        "client": client,
        "fingerprints_date": client.fingerprints_date,
        "expired_documents": expired_documents,
        "today": today,
    }


def send_expired_documents_email(client: Client, *, sent_by: AbstractBaseUser | AnonymousUser | None = None) -> int:
    """Send a summary of expired documents after fingerprints are submitted."""
    if not client.email:
        return 0

    language = _get_preferred_language(client)
    context = _get_expired_documents_context(client)
    if not context:
        return 0

    with override(language):
        subject = _get_subject("expired_documents", language)
    body = _render_email_body("expired_documents", context, language)
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="expired_documents",
        sent_by=sent_by,
        idempotency_key=build_email_idempotency_key(
            "expired_documents",
            client.pk,
            client.email,
            client.fingerprints_date,
            timezone.localdate(),
        ),
    )


def _get_missing_documents_context(client: Client, language: str | None = None) -> dict[str, Any] | None:
    if language is None:
        language = _get_preferred_language(client)
    from clients.models import DocumentRequirement
    purpose = client.get_document_requirement_purpose()
    has_db_records = DocumentRequirement.objects.filter(
        application_purpose=purpose
    ).exists()
    catalog = DocumentRequirement.catalog_for(
        purpose,
        language,
        include_optional=False,
        include_fallback=not has_db_records,
    )
    uploaded_codes = set(client.documents.values_list("document_type", flat=True))
    submitted_codes = get_submitted_document_codes(client)
    missing_zus = missing_zus_months(client)
    missing = []
    uploaded_with_expiry = []

    for item in catalog:
        code = item["code"]
        if code == DocumentType.ZUS_RCA_OR_INSURANCE.value and missing_zus:
            continue

        if code in uploaded_codes or code in submitted_codes:
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

    if missing_zus:
        with override(language):
            missing.append(
                {
                    "name": _("Нет ZUS RCA за месяцы: %(months)s.")
                    % {"months": format_zus_months(missing_zus)},
                    "expiry_date": None,
                }
            )

    if not missing:
        return None

    return {
        "client": client,
        "documents": missing,
        "uploaded_with_expiry": uploaded_with_expiry,
    }


def send_missing_documents_email(
    client: Client,
    *,
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    weekly_key: str | None = None,
    idempotency_extra: str | None = None,
) -> int:
    """Send a reminder listing documents that are still missing for the client."""

    if not client.email:
        return 0

    language = _get_preferred_language(client)
    context = _get_missing_documents_context(client, language)
    if not context:
        return 0

    subject = _get_subject("missing_documents", language)
    body = _render_email_body("missing_documents", context, language)
    today = timezone.localdate()
    iso_year, iso_week, _iso_weekday = today.isocalendar()
    idempotency_key = weekly_key or idempotency_extra or (
        f"missing_documents:{client.pk}:{iso_year}-W{iso_week:02d}"
    )
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="missing_documents",
        sent_by=sent_by,
        idempotency_key=idempotency_key,
    )


def _get_expiring_documents_context(client: Client, documents: list[Document]) -> dict[str, Any] | None:
    if not documents:
        return None

    today = timezone.localdate()
    soon_days = 3
    soon_cutoff = today + timedelta(days=soon_days)
    cutoff = today + timedelta(days=7)

    # Classify the supplied documents list
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
        doc for doc in expiring_documents if doc.expiry_date and doc.expiry_date <= soon_cutoff
    ]
    expiring_later_documents = [
        doc for doc in expiring_documents if doc.expiry_date and doc.expiry_date > soon_cutoff
    ]

    # All documents with expiry from the client (for valid/expired context)
    all_client_docs = client.documents.filter(expiry_date__isnull=False).order_by("expiry_date")
    valid_documents = [doc for doc in all_client_docs if doc.expiry_date and doc.expiry_date > cutoff]

    # Missing documents from the checklist
    checklist = client.get_document_checklist() or []
    missing_documents = []
    for item in checklist:
        if item.get("is_complete"):
            continue
        # Accessing private attribute or method from item safely
        item_docs = item.get("documents")
        latest_document = item_docs[0] if item_docs else None
        missing_documents.append(
            {
                "name": item.get("name"),
                "expiry_date": getattr(latest_document, "expiry_date", None),
            }
        )

    return {
        "client": client,
        "expired_documents": expired_documents,
        "expiring_soon_documents": expiring_soon_documents,
        "expiring_later_documents": expiring_later_documents,
        "valid_documents": valid_documents,
        "missing_documents": missing_documents,
        "today": today,
        "cutoff": cutoff,
    }


def send_expiring_documents_email(client: Client, documents: list[Document], *, sent_by: AbstractBaseUser | AnonymousUser | None = None) -> int:
    """Send a notice about documents expiring soon (within the next week)."""

    if not client.email or not documents:
        return 0

    language = _get_preferred_language(client)
    context = _get_expiring_documents_context(client, documents)
    if not context:
        return 0

    subject = _get_subject("expiring_documents", language)
    body = _render_email_body("expiring_documents", context, language)
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="expiring_documents",
        sent_by=sent_by,
        idempotency_key=build_email_idempotency_key(
            "expiring_documents",
            client.pk,
            client.email,
            sorted(f"{doc.pk}:{doc.expiry_date}" for doc in documents if doc.expiry_date),
        ),
    )


def _get_appointment_context(client: Client) -> dict[str, Any] | None:
    if not client.fingerprints_date:
        return None

    return {
        "client": client,
        "fingerprints_date": client.fingerprints_date,
        "fingerprints_time": client.fingerprints_time,
        "fingerprints_location": client.fingerprints_location,
    }


def send_appointment_notification_email(client: Client, *, sent_by: AbstractBaseUser | AnonymousUser | None = None) -> int:
    """Send a notification about a fingerprint appointment."""
    if not client.email or not client.fingerprints_date:
        return 0

    language = _get_preferred_language(client)
    context = _get_appointment_context(client)
    if not context:
        return 0

    subject = _get_subject("appointment_notification", language)
    body = _render_email_body("appointment_notification", context, language)
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="appointment_notification",
        sent_by=sent_by,
        idempotency_key=build_email_idempotency_key(
            "appointment_notification",
            client.pk,
            client.email,
            client.fingerprints_date,
            client.fingerprints_time,
            client.fingerprints_location,
        ),
    )


def send_onboarding_completed_email(client: Client) -> int:
    """Send an email notification to the assigned staff (or admin staff) when a client completes onboarding."""
    recipients = []
    if client.assigned_staff and client.assigned_staff.email:
        recipients.append(client.assigned_staff.email)
    else:
        recipients = _get_staff_recipients()
        
    if not recipients:
        return 0
        
    subject = f"Клиент {client.get_full_name()} заполнил анкету онбординга"
    review_path = reverse("clients:admin_mos_review", kwargs={"client_id": client.id})
    base_url = getattr(settings, "PUBLIC_BASE_URL", "") or getattr(settings, "SITE_URL", "")
    review_url = f"{base_url.rstrip('/')}{review_path}" if base_url else review_path
    body = (
        f"Клиент {client.get_full_name()} завершил заполнение анкеты онбординга.\n\n"
        f"Данные клиента:\n"
        f"Имя: {client.first_name}\n"
        f"Фамилия: {client.last_name}\n"
        f"Почта: {client.email or 'не указана'}\n"
        f"Телефон: {client.phone or 'не указан'}\n\n"
        f"Просмотреть анкету и утвердить ее вы можете в панели управления по ссылке:\n"
        f"{review_url}\n"
    )
    try:
        return _send_email(
            subject,
            body,
            recipients,
            client=client,
            template_type="onboarding_completed",
            idempotency_key=build_email_idempotency_key("onboarding_completed", client.pk, client.created_at),
        )
    except Exception:
        logger.exception("Failed to send onboarding completed email for client_id=%s", client.pk)
        return 0
