"""Email notification helpers for client lifecycle events."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, cast

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.template.loader import select_template
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, override
from PIL import Image, ImageDraw, ImageFont

from clients.constants import DocumentType
from clients.models import Client, Document, StaffTask
from clients.services.case_context import checklist_for_case, purpose_for_case
from clients.services.wniosek import get_submitted_document_codes
from clients.services.zus import format_zus_months, missing_zus_months

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

    from users.models import User

logger = logging.getLogger(__name__)

EMAIL_TYPE_MISSING_DOCUMENTS = "missing_documents"
EMAIL_TYPE_ZUS_RCA_MISSING = "zus_rca_missing"
EMAIL_TYPE_ZUS_RCA_INVALID = "zus_rca_invalid"
EMAIL_TYPE_ZUS_RCA_WRONG_PERIOD = "zus_rca_wrong_period"
EMAIL_TYPE_ZUS_RCA_REJECTED = "zus_rca_rejected"

EMAIL_SUBJECTS = {
    "required_documents": gettext_lazy("Список необходимых документов"),
    "expired_documents": gettext_lazy("Истекшие документы после сдачи отпечатков"),
    "missing_documents": gettext_lazy("Список недостающих документов"),
    "expiring_documents": gettext_lazy("Документы скоро истекают"),
    "appointment_notification": gettext_lazy("Уведомление о встрече"),
    "legal_stay_expiring": gettext_lazy("Истекает легальное пребывание"),
    EMAIL_TYPE_ZUS_RCA_MISSING: gettext_lazy("Отсутствует ZUS RCA или действующая страховка"),
    EMAIL_TYPE_ZUS_RCA_INVALID: gettext_lazy("Некорректный документ ZUS RCA"),
    EMAIL_TYPE_ZUS_RCA_WRONG_PERIOD: gettext_lazy("ZUS RCA за неверный период"),
    EMAIL_TYPE_ZUS_RCA_REJECTED: gettext_lazy("ZUS RCA или страховка отклонены сотрудником"),
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
    case: Any | None = None,
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
        "case": case,
        "subject": subject,
        "body": body,
        "recipients": ", ".join(recipients),
        "template_type": template_type,
        "sent_by": real_sent_by,
        "delivery_status": EmailLog.DELIVERY_STATUS_QUEUED,
        "error_message": "",
        "is_test_data": bool(getattr(client, "is_test_data", False)),
        "is_demo_data": bool(getattr(client, "is_demo_data", False)),
    }
    blocking_statuses = {
        EmailLog.DELIVERY_STATUS_QUEUED,
        EmailLog.DELIVERY_STATUS_SENT,
    }

    try:
        with transaction.atomic():
            existing = EmailLog.objects.select_for_update().filter(idempotency_key=idempotency_key).first()
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


def _send_mail_with_retry(
    subject: str,
    body: str,
    recipient_list: list[str],
    *,
    max_attempts: int | None = None,
    backoff_seconds: float | None = None,
) -> int:
    attempts_setting = max_attempts if max_attempts is not None else getattr(settings, "EMAIL_SEND_RETRY_ATTEMPTS", 3)
    attempts = max(1, int(attempts_setting or 3))
    backoff = float(
        backoff_seconds if backoff_seconds is not None else getattr(settings, "EMAIL_SEND_RETRY_BACKOFF_SECONDS", 0.25)
    )
    last_error_type = ""
    for attempt in range(1, attempts + 1):
        try:
            return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipient_list)
        except Exception as exc:
            last_error_type = type(exc).__name__
            logger.warning(
                "Notification email attempt failed: attempt=%s max_attempts=%s error_type=%s",
                attempt,
                attempts,
                last_error_type,
            )
            if attempt < attempts and backoff > 0:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"send_mail failed after {attempts} attempt(s): {last_error_type}")


def _send_email(
    subject: str,
    body: str,
    recipients: Iterable[str],
    *,
    client: Client | None = None,
    case: Any | None = None,
    template_type: str = "",
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    idempotency_key: str = "",
) -> int:
    recipient_list = list(recipients)

    # Autonomy guard: never dispatch real email for non-production records. The
    # autonomous reminder loop processes every active client, including Demo and
    # Test Center data; sending to those would bounce, pollute delivery metrics,
    # or leak. Log the attempt (so the Demo Center still shows it) but skip SMTP.
    if client is not None and (getattr(client, "is_demo_data", False) or getattr(client, "is_test_data", False)):
        from clients.models import EmailLog

        _log_email(
            subject,
            body,
            recipient_list,
            client=client,
            case=case,
            template_type=template_type,
            sent_by=sent_by,
            idempotency_key=idempotency_key,
            delivery_status=EmailLog.DELIVERY_STATUS_SKIPPED,
            error_message="non-production recipient; real send skipped",
        )
        return 0

    if not _reserve_idempotent_email_send(
        subject,
        body,
        recipient_list,
        client=client,
        case=case,
        template_type=template_type,
        sent_by=sent_by,
        idempotency_key=idempotency_key,
    ):
        return 0

    result = {"sent_count": 0}

    def _do_send() -> None:
        """Run SMTP I/O and record the final delivery status."""

        try:
            sent_count = _send_mail_with_retry(subject, body, recipient_list)
            result["sent_count"] = sent_count
            if sent_count and template_type != "onboarding_completed":
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
                    case=case,
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
                    case=case,
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
                case=case,
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
    case: Any | None = None,
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
            "case": case,
            "subject": subject,
            "body": body,
            "recipients": ", ".join(recipients),
            "template_type": template_type,
            "sent_by": real_sent_by,
            "delivery_status": delivery_status,
            "error_message": error_message,
            "is_test_data": bool(getattr(client, "is_test_data", False)),
            "is_demo_data": bool(getattr(client, "is_demo_data", False)),
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


def _staff_notification_recipients_for_client(client: Client) -> list[str]:
    # Internal notifications go to the shared office mailbox(es); there is no
    # per-client assigned staff to single out (spec §2).
    recipients: list[str] = list(_get_staff_recipients())
    return list(dict.fromkeys(email for email in recipients if email))


def notify_staff_about_fingerprint_invitation_upload(
    *,
    client: Client,
    document: Document,
    actor: AbstractBaseUser | AnonymousUser | None = None,
) -> StaffTask:
    """Create a staff-facing notification when a client uploads a fingerprints wezwanie."""

    client_detail_url = reverse("clients:client_detail", kwargs={"pk": client.pk})
    client_edit_url = reverse("clients:client_edit", kwargs={"pk": client.pk})
    document_preview_url = reverse("clients:document_preview", kwargs={"doc_id": document.pk})
    created_by = cast(
        "User | None",
        actor if actor and actor.is_authenticated and getattr(actor, "is_staff", False) else None,
    )

    task = StaffTask.objects.create(
        client=client,
        document=document,
        assignee=None,
        created_by=created_by,
        title=str(_("Клиент загрузил вызов на отпечатки пальцев")),
        description=str(
            _(
                "Клиент %(client)s загрузил документ wezwanie / приглашение на отпечатки пальцев. "
                "Откройте файл, проверьте приглашение и вручную заполните в карточке клиента "
                "поля отпечатков: дата, время и место сдачи. "
                "Документ: %(document_url)s. Карточка клиента: %(client_url)s. "
                "Быстрое редактирование клиента: %(edit_url)s."
            )
            % {
                "client": client,
                "document_url": document_preview_url,
                "client_url": client_detail_url,
                "edit_url": client_edit_url,
            }
        ),
        priority="high",
        status="open",
    )

    recipients = _staff_notification_recipients_for_client(client)
    if recipients:
        subject = str(_("Клиент загрузил wezwanie на отпечатки"))
        body = "\n".join(
            [
                str(_("Клиент загрузил приглашение на отпечатки пальцев.")),
                str(_("Клиент: %(client)s") % {"client": client}),
                str(_("ID клиента: %(client_id)s") % {"client_id": client.pk}),
                str(_("ID документа: %(document_id)s") % {"document_id": document.pk}),
                str(_("Откройте файл и вручную заполните дату, время и место отпечатков в карточке клиента.")),
                str(_("Карточка клиента: %(client_url)s") % {"client_url": client_detail_url}),
                str(_("Редактировать клиента: %(edit_url)s") % {"edit_url": client_edit_url}),
                str(_("Документ: %(document_url)s") % {"document_url": document_preview_url}),
            ]
        )
        try:
            _send_mail_with_retry(subject, body, recipients)
        except Exception as exc:  # pragma: no cover - email delivery is best-effort here
            logger.warning(
                "Failed to send fingerprint invitation staff notification: client_id=%s document_id=%s error_type=%s",
                client.pk,
                document.pk,
                type(exc).__name__,
            )

    return task


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
        nix_candidates.extend(nix_store.glob("**/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        nix_candidates.extend(nix_store.glob("**/share/fonts/truetype/noto/NotoSans-Regular.ttf"))
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
        for line in lines[start : start + max_lines_per_page]:
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
    confirmation_body = str(_("Письмо клиенту было отправлено. Во вложении находится текст отправленного письма."))
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


def _get_required_documents_context(
    client: Client,
    language: str | None = None,
    *,
    case: Any | None = None,
) -> dict[str, Any] | None:
    if language is None:
        language = _get_preferred_language(client)
    if case is None:
        from clients.services.cases import get_legacy_compatibility_case

        case = get_legacy_compatibility_case(client.pk, "required_documents")

    from clients.models import ClientDocumentRequirement
    from clients.services.case_context import checklist_for_case

    catalog = checklist_for_case(
        case,
        language,
        include_optional=False,
        include_fallback=True,
    )
    documents = [item.get("label") for item in catalog] if catalog else []
    # Append case-specific custom requirements
    custom_reqs = ClientDocumentRequirement.objects.filter(
        client=client,
        case=case,
        is_active=True,
        is_required=True,
    ).order_by("due_date", "created_at")
    for req in custom_reqs:
        documents.append(req.name)
    if not documents:
        return None
    return {
        "client": client,
        "documents": documents,
    }


def send_required_documents_email(
    client: Client,
    *,
    case: Any | None = None,
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
) -> int:
    """Send the required document checklist to the client upon account creation."""
    if not client.email:
        return 0

    if case is None:
        from clients.services.cases import get_legacy_compatibility_case

        case = get_legacy_compatibility_case(client.pk, "send_required_documents_email")

    context = _get_required_documents_context(client, case=case)
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
        case=case,
        template_type="required_documents",
        sent_by=sent_by,
        idempotency_key=build_email_idempotency_key("required_documents", client.pk, client.email, case.pk),
    )


def _get_expired_documents_context(client: Client, *, case: Any | None = None) -> dict[str, Any] | None:
    today = timezone.localdate()
    expired_documents = client.documents.filter(expiry_date__isnull=False, expiry_date__lt=today)
    if case is not None:
        expired_documents = expired_documents.filter(case=case)
    expired_documents = expired_documents.order_by("expiry_date")
    if not expired_documents.exists():
        return None

    if case is None:
        from clients.services.cases import resolve_single_active_case

        case = resolve_single_active_case(client)
    return {
        "client": client,
        "fingerprints_date": case.fingerprints_date if case else None,
        "expired_documents": expired_documents,
        "today": today,
    }


def send_expired_documents_email(
    client: Client, *, sent_by: AbstractBaseUser | AnonymousUser | None = None, case: Any | None = None
) -> int:
    """Send a summary of expired documents after fingerprints are submitted."""
    if not client.email:
        return 0

    language = _get_preferred_language(client)
    context = _get_expired_documents_context(client, case=case)
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
        case=case,
        idempotency_key=build_email_idempotency_key(
            "expired_documents",
            client.pk,
            client.email,
            getattr(case, "pk", None),
            getattr(case, "fingerprints_date", None) or client.effective_fingerprints_date,
            timezone.localdate(),
        ),
    )


def _get_missing_documents_context(
    client: Client,
    language: str | None = None,
    *,
    today: Any | None = None,
    case: Any | None = None,
) -> dict[str, Any] | None:
    if language is None:
        language = _get_preferred_language(client)
    from clients.models import ClientDocumentRequirement, DocumentRequirement

    purpose = purpose_for_case(case) if case is not None else client.get_document_requirement_purpose()
    has_db_records = DocumentRequirement.objects.filter(application_purpose=purpose).exists()
    catalog = (
        checklist_for_case(case, language, include_optional=False, include_fallback=not has_db_records)
        if case is not None
        else DocumentRequirement.catalog_for(
            purpose,
            language,
            include_optional=False,
            include_fallback=not has_db_records,
        )
    )
    # When a specific case is supplied, the checklist is scoped to that case so a
    # client with several active cases never has one case's documents counted
    # against another (spec §9). Without a case the legacy client-wide view is
    # kept for backwards compatibility.
    documents = client.documents.filter(case=case) if case is not None else client.documents.all()
    uploaded_codes = set(documents.values_list("document_type", flat=True))
    submitted_codes = get_submitted_document_codes(client, case=case)
    from clients.services.cases import resolve_single_active_case

    zus_case = case or resolve_single_active_case(client)
    missing_zus = missing_zus_months(zus_case, today=today) if zus_case else []
    missing = []
    uploaded_with_expiry = []

    for item in catalog:
        code = item["code"]
        if code == DocumentType.ZUS_RCA_OR_INSURANCE.value and missing_zus:
            continue

        if code in uploaded_codes or code in submitted_codes:
            doc = documents.filter(document_type=code).order_by("-uploaded_at").first()
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

    # Append case-specific custom requirements that are still missing
    custom_reqs = ClientDocumentRequirement.objects.filter(
        client=client,
        is_active=True,
        is_required=True,
    ).order_by("due_date", "created_at")
    if case is not None:
        custom_reqs = custom_reqs.filter(case=case)
    for req in custom_reqs:
        if req.document_type not in uploaded_codes and req.document_type not in submitted_codes:
            missing.append(
                {
                    "name": req.name,
                    "expiry_date": req.due_date,
                }
            )

    if missing_zus:
        with override(language):
            missing.append(
                {
                    "name": _("Нет ZUS RCA за месяцы: %(months)s.") % {"months": format_zus_months(missing_zus)},
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
    today: Any | None = None,
    case: Any | None = None,
) -> int:
    """Send a reminder listing documents that are still missing for the client.

    ``case`` scopes the checklist and the default idempotency key to a single
    case, so a multi-case client receives a separate, correct reminder per case
    instead of one merged email or a silently suppressed second case (spec §9).
    """

    if not client.email:
        return 0

    language = _get_preferred_language(client)
    context = _get_missing_documents_context(client, language, today=today, case=case)
    if not context:
        return 0

    subject = _get_subject("missing_documents", language)
    body = _render_email_body("missing_documents", context, language)
    today = today or timezone.localdate()
    iso_year, iso_week, _iso_weekday = today.isocalendar()
    case_segment = f"{case.pk}:" if case is not None else ""
    idempotency_key = (
        weekly_key or idempotency_extra or (f"missing_documents:{client.pk}:{case_segment}{iso_year}-W{iso_week:02d}")
    )
    return _send_email(
        subject,
        body,
        [client.email],
        client=client,
        template_type="missing_documents",
        sent_by=sent_by,
        case=case,
        idempotency_key=idempotency_key,
    )


def _get_expiring_documents_context(
    client: Client, documents: list[Document], *, case: Any | None = None
) -> dict[str, Any] | None:
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

    expiring_soon_documents = [doc for doc in expiring_documents if doc.expiry_date and doc.expiry_date <= soon_cutoff]
    expiring_later_documents = [doc for doc in expiring_documents if doc.expiry_date and doc.expiry_date > soon_cutoff]

    # All documents with expiry from the client (for valid/expired context)
    all_client_docs = client.documents.filter(expiry_date__isnull=False)
    if case is not None:
        all_client_docs = all_client_docs.filter(case=case)
    all_client_docs = all_client_docs.order_by("expiry_date")
    valid_documents = [doc for doc in all_client_docs if doc.expiry_date and doc.expiry_date > cutoff]

    # Missing documents from the checklist
    checklist = client.get_document_checklist(case=case) if case is not None else client.get_document_checklist() or []
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


def send_expiring_documents_email(
    client: Client,
    documents: list[Document],
    *,
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
    case: Any | None = None,
) -> int:
    """Send a notice about documents expiring soon (within the next week)."""

    if not client.email or not documents:
        return 0

    if case is None:
        case_ids = {document.case_id for document in documents if document.case_id}
        if len(case_ids) == 1:
            from clients.models import Case

            case = Case.objects.filter(pk=case_ids.pop()).first()
    elif any(document.case_id and document.case_id != case.pk for document in documents):
        raise ValueError("All expiring documents must belong to the supplied case.")

    language = _get_preferred_language(client)
    context = _get_expiring_documents_context(client, documents, case=case)
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
        case=case,
        idempotency_key=build_email_idempotency_key(
            "expiring_documents",
            client.pk,
            client.email,
            getattr(case, "pk", None),
            sorted(f"{doc.pk}:{doc.expiry_date}" for doc in documents if doc.expiry_date),
        ),
    )


def _get_appointment_context(client: Client, *, case: Any | None = None) -> dict[str, Any] | None:
    # Fingerprints data lives on the case. New callers pass it explicitly; the
    # legacy fallback is kept only for unambiguous single-case flows.
    if case is None:
        from clients.services.cases import resolve_single_active_case

        case = resolve_single_active_case(client)
    if case is None or not case.fingerprints_date:
        return None

    return {
        "client": client,
        "fingerprints_date": case.fingerprints_date,
        "fingerprints_time": case.fingerprints_time,
        "fingerprints_location": case.fingerprints_location,
    }


def send_appointment_notification_email(
    client: Client, *, sent_by: AbstractBaseUser | AnonymousUser | None = None, case: Any | None = None
) -> int:
    """Send a notification about a fingerprint appointment."""
    if not client.email:
        return 0

    language = _get_preferred_language(client)
    context = _get_appointment_context(client, case=case)
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
        case=case,
        idempotency_key=build_email_idempotency_key(
            "appointment_notification",
            client.pk,
            client.email,
            getattr(case, "pk", None),
            context["fingerprints_date"],
            context["fingerprints_time"],
            context["fingerprints_location"],
        ),
    )


def send_onboarding_completed_email(client: Client) -> int:
    """Send an email notification to the office staff when a client completes onboarding."""
    recipients = _get_staff_recipients()

    if not recipients:
        return 0

    subject = _("Клиент %(name)s заполнил анкету онбординга") % {"name": client.get_full_name()}
    review_path = reverse("clients:admin_mos_review", kwargs={"client_id": client.id})
    base_url = getattr(settings, "PUBLIC_BASE_URL", "") or getattr(settings, "SITE_URL", "")
    review_url = f"{base_url.rstrip('/')}{review_path}" if base_url else review_path
    body = _(
        "Клиент %(name)s завершил заполнение анкеты онбординга.\n\n"
        "Данные клиента:\n"
        "Имя: %(first_name)s\n"
        "Фамилия: %(last_name)s\n"
        "Почта: %(email)s\n"
        "Телефон: %(phone)s\n\n"
        "Просмотреть анкету и утвердить ее вы можете в панели управления по ссылке:\n"
        "%(review_url)s\n"
    ) % {
        "name": client.get_full_name(),
        "first_name": client.first_name,
        "last_name": client.last_name,
        "email": client.email or _("не указана"),
        "phone": client.phone or _("не указан"),
        "review_url": review_url,
    }
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


def send_legal_stay_email(
    client: Client,
    legal_stay_until: Any,
    due_date: Any,
    *,
    sent_by: AbstractBaseUser | AnonymousUser | None = None,
) -> int:
    """Send a notification about the client's legal stay expiring soon."""
    if not client.email:
        return 0

    from datetime import date

    from django.utils import timezone

    today = timezone.localdate()
    if hasattr(legal_stay_until, "date"):
        stay_date = legal_stay_until.date()
    else:
        stay_date = legal_stay_until

    days_left = (stay_date - today).days

    language = _get_preferred_language(client)
    context = {
        "client": client,
        "legal_stay_until": legal_stay_until,
        "due_date": due_date,
    }
    subject = _get_subject("legal_stay_expiring", language)
    body = _render_email_body("legal_stay", context, language)

    if days_left <= 14:
        recipients = [client.email]
        recipients.extend(_get_staff_recipients())

        days_epoch = (today - date(2026, 1, 1)).days
        interval = days_epoch // 3

        idempotency_key = build_email_idempotency_key(
            "legal_stay_expiring_critical",
            client.pk,
            client.email,
            legal_stay_until,
            interval,
        )
        return _send_email(
            subject,
            body,
            recipients,
            client=client,
            template_type="legal_stay_expiring",
            sent_by=sent_by,
            idempotency_key=idempotency_key,
        )
    else:
        return _send_email(
            subject,
            body,
            [client.email],
            client=client,
            template_type="legal_stay_expiring",
            sent_by=sent_by,
            idempotency_key=build_email_idempotency_key(
                "legal_stay_expiring",
                client.pk,
                client.email,
                legal_stay_until,
            ),
        )
