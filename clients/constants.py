from legalize_site.constants import (
    DOCUMENT_CHECKLIST,
    FAMILY_CHILD_DOCS,
    FAMILY_SPOUSE_DOCS,
    STUDY_DOCS,
    WORK_DOCS,
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
    'SELF_ONBOARDING_SLUG',
    'FINISHED_WORKFLOW_STAGES',
    'ACTIVE_WORKFLOW_STAGES',
    'is_company_document_type',
    'is_passport_document_type',
    'is_rental_document_type',
    'is_zus_document_type',
    'is_insurance_document_type',
]

INTERNAL_DOCS = {
    DocumentType.WEZWANIE,
    DocumentType.FINGERPRINT_CONFIRMATION,
    DocumentType.PAYMENT_CONFIRMATION,
    DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION,
}

SELF_ONBOARDING_SLUG = "me"

# Workflow stages that represent finished work (a case no longer needs active
# attention). Used to scope dashboards/queues/metrics to active cases (spec §4).
FINISHED_WORKFLOW_STAGES = ("closed", "decision_received")
ACTIVE_WORKFLOW_STAGES = (
    "new_client",
    "document_collection",
    "application_submitted",
    "fingerprints",
    "waiting_decision",
)

WEZWANIE_DOCUMENT_TYPES = {
    DocumentType.WEZWANIE.value,
    DocumentType.FINGERPRINT_CONFIRMATION.value,
    "formal_deficiencies",
    "formal_deficiencies_wezwanie",
    "braki_formalne",
    "braki_formalne_wezwanie",
}

COMPANY_DOCUMENT_TYPES = {
    DocumentType.ZALACZNIK_NR_1.value,       # 'załącznik_nr_1'
    DocumentType.EMPLOYMENT_CONTRACT.value,  # 'employment_contract'
    DocumentType.WORK_PERMISSION.value,      # 'work_permission'
}


def is_wezwanie_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a summons-like type that requires OCR."""
    if not doc_type:
        return False
    return str(doc_type).lower() in WEZWANIE_DOCUMENT_TYPES


def is_company_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a company document that requires registry verification."""
    if not doc_type:
        return False
    return str(doc_type).lower() in COMPANY_DOCUMENT_TYPES


def is_passport_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a passport."""
    if not doc_type:
        return False
    return str(doc_type).lower() == DocumentType.PASSPORT.value


def is_rental_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a rental agreement."""
    if not doc_type:
        return False
    return str(doc_type).lower() == DocumentType.ADDRESS_PROOF.value


def is_zus_document_type(doc_type: str | None) -> bool:
    """Check if the document type is ZUS registration or contribution history."""
    if not doc_type:
        return False
    return str(doc_type).lower() in {
        DocumentType.ZUS_RCA_OR_INSURANCE.value,
        DocumentType.ZUS_CONTRIBUTION_HISTORY.value
    }


def is_insurance_document_type(doc_type: str | None) -> bool:
    """Check if the document type is a health insurance policy."""
    if not doc_type:
        return False
    return str(doc_type).lower() == DocumentType.HEALTH_INSURANCE.value


def is_recurring_document_type(doc_type: str | None) -> bool:
    """Recurring documents are re-supplied over time (e.g. the monthly ZUS RCA
    declaration), so the portal keeps their upload control available even after
    a period has been accepted."""
    if not doc_type:
        return False
    return str(doc_type).lower() == DocumentType.ZUS_RCA_OR_INSURANCE.value
