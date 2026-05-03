from legalize_site.constants import (
    DOCUMENT_CHECKLIST,
    STUDY_DOCS,
    WORK_DOCS,
    FAMILY_CHILD_DOCS,
    FAMILY_SPOUSE_DOCS,
    DocumentType,
    doc_entry,
)

__all__ = [
    'DocumentType',
    'doc_entry',
    'STUDY_DOCS',
    'WORK_DOCS',
    'FAMILY_SPOUSE_DOCS',
    'FAMILY_CHILD_DOCS',
    'DOCUMENT_CHECKLIST',
    'INTERNAL_DOCS',
]

INTERNAL_DOCS = {
    DocumentType.WEZWANIE,
    DocumentType.FINGERPRINT_CONFIRMATION,
    DocumentType.PAYMENT_CONFIRMATION,
}

WEZWANIE_DOCUMENT_TYPES = {
    DocumentType.WEZWANIE.value,
    DocumentType.FINGERPRINT_CONFIRMATION.value,
    "formal_deficiencies",
    "formal_deficiencies_wezwanie",
    "braki_formalne",
    "braki_formalne_wezwanie",
}


def is_wezwanie_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a summons-like type that requires OCR."""
    if not doc_type:
        return False
    return str(doc_type).lower() in WEZWANIE_DOCUMENT_TYPES
