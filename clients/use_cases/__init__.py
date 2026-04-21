"""Explicit application use cases for the clients domain."""

from clients.use_cases.documents import (
    ClientNoteScenarioResult,
    DocumentScenarioResult,
    WniosekAttachmentScenarioResult,
    delete_client_document,
    delete_wniosek_attachment,
    record_document_download,
    toggle_client_document_verification,
    update_client_notes_for_client,
    verify_all_client_documents,
)
from clients.use_cases.client_records import (
    CLIENT_UPDATE_TRACKED_FIELDS,
    ClientRecordScenarioResult,
    finalize_client_creation,
    finalize_client_update,
    snapshot_client_update_state,
)
from clients.use_cases.document_requirements import (
    DocumentRequirementScenarioResult,
    build_document_requirement_code,
    create_document_requirement_for_purpose,
    delete_document_requirement_record,
    sync_document_checklist_for_purpose,
    update_document_requirement_record,
)
from clients.use_cases.exports import (
    ExportScenarioResult,
    record_client_export,
    restore_document_version_for_client,
)
from clients.use_cases.payments import (
    PAYMENT_MUTABLE_FIELDS,
    PaymentScenarioResult,
    create_payment_for_client,
    delete_payment_for_client,
    update_payment_for_client,
)
from clients.use_cases.reminders import (
    ReminderScenarioResult,
    deactivate_reminder,
    delete_reminder,
    send_document_reminder_for_client,
    send_document_reminder_for_reminder,
)
from clients.use_cases.tasks import (
    TaskScenarioResult,
    complete_task_for_client,
    create_task_for_client,
)

__all__ = [
    "ClientNoteScenarioResult",
    "ClientRecordScenarioResult",
    "DocumentScenarioResult",
    "DocumentRequirementScenarioResult",
    "WniosekAttachmentScenarioResult",
    "ExportScenarioResult",
    "CLIENT_UPDATE_TRACKED_FIELDS",
    "PAYMENT_MUTABLE_FIELDS",
    "PaymentScenarioResult",
    "ReminderScenarioResult",
    "TaskScenarioResult",
    "update_client_notes_for_client",
    "delete_client_document",
    "delete_wniosek_attachment",
    "toggle_client_document_verification",
    "verify_all_client_documents",
    "record_document_download",
    "snapshot_client_update_state",
    "finalize_client_creation",
    "finalize_client_update",
    "build_document_requirement_code",
    "create_document_requirement_for_purpose",
    "update_document_requirement_record",
    "delete_document_requirement_record",
    "sync_document_checklist_for_purpose",
    "record_client_export",
    "restore_document_version_for_client",
    "create_task_for_client",
    "complete_task_for_client",
    "create_payment_for_client",
    "update_payment_for_client",
    "delete_payment_for_client",
    "deactivate_reminder",
    "delete_reminder",
    "send_document_reminder_for_client",
    "send_document_reminder_for_reminder",
]
