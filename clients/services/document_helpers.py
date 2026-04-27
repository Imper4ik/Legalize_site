import logging
from typing import Any

logger = logging.getLogger(__name__)

def document_file_exists(document: Any) -> bool:
    """Check if the physical file for a document exists in storage."""
    if not document.file:
        return False
    try:
        return document.file.storage.exists(document.file.name)
    except Exception:
        logger.exception("Could not check document file existence: document_id=%s", document.pk)
        return False
