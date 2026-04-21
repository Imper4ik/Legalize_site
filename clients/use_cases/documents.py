from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from clients.models import Client, Document, WniosekAttachment
from clients.services.activity import log_client_activity
from clients.services.notifications import send_missing_documents_email

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


def update_client_notes_for_client(*, client: Client, actor, notes: str) -> ClientNoteScenarioResult:
    client.notes = notes
    client.save(update_fields=["notes"])
    log_client_activity(
        client=client,
        actor=actor,
        event_type="note_updated",
        summary="Обновлена заметка по клиенту",
    )
    return ClientNoteScenarioResult(client=client, notes=client.notes or "")


def delete_client_document(*, document: Document, actor) -> DocumentScenarioResult:
    client = document.client
    document_id = document.pk
    document_display_name = document.display_name

    log_client_activity(
        client=client,
        actor=actor,
        event_type="document_deleted",
        summary=f"Удалён документ: {document_display_name}",
        metadata={"document_id": document_id, "document_type": document.document_type},
    )
    document.delete()

    return DocumentScenarioResult(
        client=client,
        deleted_document_id=document_id,
        document_display_name=document_display_name,
    )


def delete_wniosek_attachment(*, attachment: WniosekAttachment, actor) -> WniosekAttachmentScenarioResult:
    submission = attachment.submission
    client = submission.client
    attachment_id = attachment.pk
    attachment_name = attachment.entered_name
    document_type = attachment.document_type
    submission_id = submission.pk

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
        summary=f"Удалена отметка wniosek: {attachment_name}",
        metadata={
            "attachment_id": attachment_id,
            "attachment_name": attachment_name,
            "document_type": document_type,
            "submission_id": submission_id,
            "remaining_count": remaining_count,
            "submission_deleted": submission_deleted,
        },
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
    actor,
    send_missing_email: MissingDocumentsSender = send_missing_documents_email,
) -> DocumentScenarioResult:
    was_verified = document.verified
    document.verified = not document.verified
    document.save(update_fields=["verified"])

    log_client_activity(
        client=document.client,
        actor=actor,
        event_type="document_verified",
        summary=f"Статус документа изменён: {document.display_name}",
        details="verified" if document.verified else "verification removed",
        metadata={"document_id": document.id, "verified": document.verified},
        document=document,
    )

    emails_sent = False
    if document.verified and not was_verified:
        emails_sent = bool(send_missing_email(document.client))

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
    actor,
    send_missing_email: MissingDocumentsSender = send_missing_documents_email,
) -> DocumentScenarioResult:
    updated_count = client.documents.filter(verified=False).update(verified=True)
    if updated_count:
        log_client_activity(
            client=client,
            actor=actor,
            event_type="document_verified",
            summary="Все документы клиента отмечены как проверенные",
            metadata={"verified_count": updated_count},
        )

    emails_sent = False
    if updated_count:
        emails_sent = bool(send_missing_email(client))

    return DocumentScenarioResult(
        client=client,
        updated_count=updated_count,
        emails_sent=emails_sent,
    )


def record_document_download(*, document: Document, actor) -> DocumentScenarioResult:
    log_client_activity(
        client=document.client,
        actor=actor,
        event_type="document_downloaded",
        summary=f"Открыт документ: {document.display_name}",
        metadata={"document_id": document.id, "document_type": document.document_type},
        document=document,
    )
    return DocumentScenarioResult(
        client=document.client,
        document=document,
        document_display_name=document.display_name,
    )
