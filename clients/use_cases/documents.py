from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from clients.models import Client, Document, WniosekAttachment
from clients.security.sanitizer import sanitize_user_html
from clients.services.activity import log_client_activity
from clients.services.notifications import send_missing_documents_email

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)

MissingDocumentsSender = Callable[[Client], int]


@dataclass(frozen=True)
class ClientNoteScenarioResult:
    client: Client
    notes: str


@dataclass(frozen=True)
class DocumentScenarioResult:
    client: Client
    document: Document | None = None
    verified: bool | None = None
    emails_sent: bool = False
    updated_count: int = 0
    deleted_document_id: int | None = None
    document_display_name: str = ""


@dataclass(frozen=True)
class WniosekAttachmentScenarioResult:
    client: Client
    deleted_attachment_id: int
    attachment_name: str
    remaining_count: int
    submission_deleted: bool


def _safe_send_missing_documents_email(
    client: Client,
    send_missing_email: MissingDocumentsSender,
) -> bool:
    """Send missing-documents email without breaking AJAX document actions.

    Verification itself should not fail just because SMTP/template delivery had
    a temporary error. The caller can still see emails_sent=False, while the
    backend logs the real delivery problem.
    """
    try:
        return bool(send_missing_email(client))
    except Exception:
        logger.exception("Failed to send missing-documents email for client_id=%s", client.pk)
        return False


def update_client_notes_for_client(*, client: Client, actor: AbstractBaseUser | AnonymousUser | None, notes: str) -> ClientNoteScenarioResult:
    cleaned_notes = sanitize_user_html(notes)
    with transaction.atomic():
        client.notes = cleaned_notes
        client.save(update_fields=["notes"])
        log_client_activity(
            client=client,
            actor=actor,
            event_type="note_updated",
            summary="Обновлена заметка по клиенту",
        )
    return ClientNoteScenarioResult(client=client, notes=client.notes or "")


def delete_client_document(*, document: Document, actor: AbstractBaseUser | AnonymousUser | None) -> DocumentScenarioResult:
    client = document.client
    document_id = document.pk
    document_display_name = document.display_name

    with transaction.atomic():
        log_client_activity(
            client=client,
            actor=actor,
            event_type="document_deleted",
            summary="Документ удалён",
            metadata={"document_id": document_id},
            document=document,
        )
        document.archive()

    return DocumentScenarioResult(
        client=client,
        document=document,
        deleted_document_id=document_id,
        document_display_name=document_display_name,
    )


def delete_wniosek_attachment(*, attachment: WniosekAttachment, actor: AbstractBaseUser | AnonymousUser | None) -> WniosekAttachmentScenarioResult:
    submission = attachment.submission
    client = submission.client
    attachment_id = attachment.pk
    attachment_name = attachment.entered_name

    with transaction.atomic():
        attachment.delete()
        remaining_count = submission.attachments.count()
        submission_deleted = remaining_count == 0
        if submission_deleted:
            submission.delete()
        elif submission.attachment_count != remaining_count:
            submission.attachment_count = remaining_count
            submission.save(update_fields=["attachment_count"])

        log_client_activity(
            client=client,
            actor=actor,
            event_type="wniosek_attachment_deleted",
            summary="Отметка wniosek удалена",
            metadata={},
        )

    return WniosekAttachmentScenarioResult(
        client=client,
        deleted_attachment_id=attachment_id,
        attachment_name=attachment_name,
        remaining_count=remaining_count,
        submission_deleted=submission_deleted,
    )


def toggle_client_document_verification(
    *,
    document: Document,
    actor: AbstractBaseUser | AnonymousUser | None,
    send_missing_email: MissingDocumentsSender = send_missing_documents_email,
) -> DocumentScenarioResult:
    was_verified = document.verified
    with transaction.atomic():
        document.verified = not document.verified
        if document.verified:
            document.awaiting_confirmation = False
            document.rejection_reason = ""
            document.save(update_fields=["verified", "awaiting_confirmation", "rejection_reason"])
        else:
            document.save(update_fields=["verified"])

        if document.verified:
            from clients.services.tasks import close_auto_task
            close_auto_task(document.client, "document_review", document=document)

        log_client_activity(
            client=document.client,
            actor=actor,
            event_type="document_verified",
            summary="Статус документа изменён",
            details="",
            metadata={"document_id": document.id, "verified": document.verified},
            document=document,
        )

    emails_sent = False
    if document.verified and not was_verified:
        emails_sent = _safe_send_missing_documents_email(document.client, send_missing_email)

    return DocumentScenarioResult(
        client=document.client,
        document=document,
        verified=document.verified,
        emails_sent=emails_sent,
        document_display_name=document.display_name,
    )


def verify_all_client_documents(
    *,
    client: Client,
    actor: AbstractBaseUser | AnonymousUser | None,
    send_missing_email: MissingDocumentsSender = send_missing_documents_email,
) -> DocumentScenarioResult:
    with transaction.atomic():
        from django.db.models import Q
        from django.utils import timezone
        today = timezone.localdate()
        updated_count = (
            client.documents.filter(verified=False, archived_at__isnull=True)
            .exclude(expiry_date__isnull=False, expiry_date__lt=today)
            .exclude(Q(rejection_reason__isnull=False) & ~Q(rejection_reason=""))
            .update(verified=True, awaiting_confirmation=False)
        )
        if updated_count:
            from clients.services.tasks import close_auto_task
            close_auto_task(client, "document_review")

            log_client_activity(
                client=client,
                actor=actor,
                event_type="document_verified",
                summary="Сотрудник подтвердил документы через массовое действие",
                metadata={"verified_count": updated_count},
            )

    emails_sent = False
    if updated_count:
        emails_sent = _safe_send_missing_documents_email(client, send_missing_email)

    return DocumentScenarioResult(
        client=client,
        updated_count=updated_count,
        emails_sent=emails_sent,
    )


def record_document_download(*, document: Document, actor: AbstractBaseUser | AnonymousUser | None) -> DocumentScenarioResult:
    log_client_activity(
        client=document.client,
        actor=actor,
        event_type="document_downloaded",
        summary="Документ открыт",
        metadata={"document_id": document.id},
        document=document,
    )
    return DocumentScenarioResult(
        client=document.client,
        document=document,
        document_display_name=document.display_name,
    )
