import logging
import os
from collections.abc import Mapping
from typing import Any

from django.core.files.base import ContentFile

from clients.models import Case, Document

logger = logging.getLogger(__name__)


def document_has_ocr_warning(document: Any) -> bool:
    """Return whether a document contains an actionable OCR warning.

    ``EncryptedJSONField`` deliberately returns a non-dict unavailable marker
    when its ciphertext cannot be decrypted. Treat that marker (and malformed
    legacy values) as unreadable, not as an OCR warning, so callers can keep
    scanning other document versions without calling ``.get`` on a string.
    """
    if bool(getattr(document, "ocr_name_mismatch", False)):
        return True

    parsed_data = getattr(document, "parsed_data", None)
    return isinstance(parsed_data, Mapping) and bool(parsed_data.get("warnings"))


def document_file_exists(document: Any) -> bool:
    """Check if the physical file for a document exists in storage."""
    if not document.file:
        return False
    try:
        return document.file.storage.exists(document.file.name)
    except Exception:
        logger.exception("Could not check document file existence: document_id=%s", document.pk)
        return False


def copy_document_to_case(document: Document, target_case: Case) -> Document:
    """Creates a copy of a Document record for a new case, copying the file in storage."""
    new_doc = Document(
        client=target_case.client,
        case=target_case,
        document_type=document.document_type,
        expiry_date=document.expiry_date,
        zus_period_month=document.zus_period_month,
        awaiting_confirmation=document.awaiting_confirmation,
        rejection_reason=document.rejection_reason,
        ocr_status=document.ocr_status,
        ocr_name_mismatch=document.ocr_name_mismatch,
        parsed_data=document.parsed_data,
        is_test_data=document.is_test_data,
        is_demo_data=document.is_demo_data,
        copied_from_document=document,
    )
    if document.file:
        try:
            document.file.seek(0)
            content = document.file.read()
            document.file.seek(0)
            filename = os.path.basename(document.file.name or "")
            new_doc.file.save(filename, ContentFile(content), save=False)
        except Exception:
            logger.exception("Failed to physically copy document file, referencing original: document_id=%s", document.pk)
            new_doc.file = document.file
    new_doc.save()
    return new_doc
