from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from clients.models import Document, DocumentVersion


def archive_document_version(
    document: Document,
    *,
    uploaded_by=None,
    comment: str = "",
) -> DocumentVersion | None:
    """Persist the current file as a historical document version."""

    if not document.file:
        return None

    current_max = document.versions.aggregate(max_v=Max("version_number"))["max_v"] or 0
    return DocumentVersion.objects.create(
        document=document,
        file=document.file,
        version_number=current_max + 1,
        uploaded_by=uploaded_by,
        comment=comment,
        file_name=Path(document.file.name).name,
        file_size=document.file.size,
    )


def replace_document_file(
    document: Document,
    *,
    uploaded_file,
    expiry_date=None,
) -> Document:
    """Replace the active document file and reset file-derived state."""

    document.file = uploaded_file
    if expiry_date:
        document.expiry_date = expiry_date
    document.verified = False
    document.awaiting_confirmation = False
    document.ocr_status = "skipped"
    document.ocr_name_mismatch = False
    document.save()
    return document


def restore_document_version(version: DocumentVersion, *, uploaded_by=None) -> Document:
    """Restore a stored version and archive the previously active file."""

    document = version.document
    with transaction.atomic():
        archive_document_version(
            document,
            uploaded_by=uploaded_by,
            comment=_("Automatic archive before restoring version %(num)s")
            % {"num": version.version_number},
        )

        version.file.open("rb")
        try:
            restored_content = version.file.read()
        finally:
            version.file.close()

        ext = Path(version.file.name).suffix or ".bin"
        new_name = f"documents/restored_{document.pk}{ext}"
        document.file.save(new_name, ContentFile(restored_content), save=False)
        document.verified = False
        document.awaiting_confirmation = False
        document.ocr_status = "skipped"
        document.ocr_name_mismatch = False
        document.save()

    return document
