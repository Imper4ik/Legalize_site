from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from clients.models import Client, Document, DocumentVersion
from clients.services.activity import log_client_activity
from clients.services.document_versions import restore_document_version


@dataclass(frozen=True)
class ExportScenarioResult:
    client: Client
    export_type: str | None = None
    document: Document | None = None
    version: DocumentVersion | None = None
    metadata: dict[str, object] = field(default_factory=dict)


def record_client_export(
    *,
    client: Client,
    actor,
    export_type: str,
    metadata: Mapping[str, object] | None = None,
    summary: str | None = None,
) -> ExportScenarioResult:
    metadata_dict = {"export_type": export_type}
    if metadata:
        metadata_dict.update(dict(metadata))

    log_client_activity(
        client=client,
        actor=actor,
        event_type="client_exported",
        summary=summary or f"Экспорт кейса ({export_type})",
        metadata=metadata_dict,
    )
    return ExportScenarioResult(
        client=client,
        export_type=export_type,
        metadata=metadata_dict,
    )


def restore_document_version_for_client(
    *,
    version: DocumentVersion,
    actor,
) -> ExportScenarioResult:
    uploaded_by = actor if getattr(actor, "is_authenticated", False) else None
    document = restore_document_version(version, uploaded_by=uploaded_by)

    metadata = {
        "restored_version_id": version.pk,
        "restored_version_number": version.version_number,
        "restored_from_file": version.file_name,
    }
    log_client_activity(
        client=document.client,
        actor=actor,
        event_type="document_version_restored",
        summary=f"Документ восстановлен к v{version.version_number}",
        document=document,
        metadata=metadata,
    )
    return ExportScenarioResult(
        client=document.client,
        document=document,
        version=version,
        metadata=metadata,
    )
