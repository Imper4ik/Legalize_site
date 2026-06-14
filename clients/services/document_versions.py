from __future__ import annotations

import logging
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from clients.models import Document, DocumentVersion

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)


def archive_document_version(
    document: Document,
    *,
    uploaded_by: AbstractBaseUser | AnonymousUser | None = None,
    comment: str = "",
) -> DocumentVersion | None:
    """Persist the current file as a historical document version by making a physical copy."""

    if not document.file:
        return None
    if not document.file.name:
        return None

    try:
        document.file.open("rb")
        content = document.file.read()
        file_size = len(content)
    except (FileNotFoundError, OSError):
        logger.warning(
            "Skipping document version archive because the source file is missing: "
            "document_id=%s",
            document.pk,
        )
        return None
    finally:
        with suppress(Exception):
            document.file.close()

    current_max = document.versions.aggregate(max_v=Max("version_number"))["max_v"] or 0
    version_number = int(current_max) + 1

    file_name_attr = str(document.file.name)
    ext = Path(file_name_attr).suffix or ".bin"
    file_name = f"document_{document.pk}_v{version_number}{ext}"
    # Ensure a unique path for the version file
    new_path = f"document_versions/{document.pk}_v{version_number}{ext}"

    # AnonymousUser cannot be assigned to ForeignKey
    real_uploaded_by = uploaded_by if uploaded_by and uploaded_by.is_authenticated else None

    version = DocumentVersion(
        document=document,
        version_number=version_number,
        uploaded_by=cast(Any, real_uploaded_by),
        comment=comment,
        file_name=file_name,
        file_size=file_size,
    )
    # Physically save the content to a new file path
    version.file.save(new_path, ContentFile(content), save=False)
    version.save()

    logger.info(
        "Archived document version: doc_id=%s, version=%s",
        document.pk, version_number
    )
    return version


def replace_document_file(
    document: Document,
    *,
    uploaded_file: Any,
    expiry_date: date | None = None,
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


def restore_document_version(version: DocumentVersion, *, uploaded_by: AbstractBaseUser | AnonymousUser | None = None) -> Document:
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

        file_name_attr = str(version.file.name)
        ext = Path(file_name_attr).suffix or ".bin"
        new_name = f"documents/restored_{document.pk}{ext}"
        document.file.save(new_name, ContentFile(restored_content), save=False)
        document.verified = False
        document.awaiting_confirmation = False
        document.ocr_status = "skipped"
        document.ocr_name_mismatch = False
        document.save()

    return document
