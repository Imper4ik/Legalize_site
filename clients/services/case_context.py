from __future__ import annotations

from datetime import date
from typing import Any

from django.db import models
from django.utils import translation

from clients.models import ClientDocumentRequirement, Document, DocumentRequirement
from clients.services.onboarding_purposes import purpose_label


def purpose_for_case(case: Any) -> str:
    """Return the document-requirement purpose for a concrete Case.

    Case is the owner of process data. The client-level application purpose is
    retained only as a legacy fallback for old cases that have not been
    backfilled yet; new process code should pass the selected case instead of
    reading Client.application_purpose directly.
    """

    case_purpose = str(getattr(case, "application_purpose", "") or "").strip()
    if case_purpose:
        family_role = str(getattr(case, "family_role", "") or "").strip()
        if case_purpose == "family" and family_role and family_role != "sponsor":
            return family_role
        if case_purpose == "family" and family_role == "sponsor":
            return "work"
        return case_purpose

    client = getattr(case, "client", None)
    if client is not None:
        return str(client.get_document_requirement_purpose())
    return ""


def checklist_for_case(
    case: Any,
    language: str | None = None,
    *,
    include_optional: bool = True,
    include_fallback: bool = True,
) -> list[dict[str, Any]]:
    """Return document requirements for the selected Case only."""

    purpose = purpose_for_case(case)
    return DocumentRequirement.catalog_for(
        purpose,
        language or translation.get_language(),
        include_optional=include_optional,
        include_fallback=include_fallback,
    )


def build_case_document_checklist(
    case: Any,
    *,
    check_file_existence: bool = False,
    requirements_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the required-document checklist for one concrete Case.

    This is the canonical Case-first checklist builder. It resolves the
    requirement purpose from the supplied case, reads uploads only from that
    case, and scopes submitted Wniosek attachments to the same case so Case A
    cannot complete Case B's checklist.
    """

    from clients.constants import DocumentType
    from clients.models.document import resolve_document_label
    from clients.services.document_helpers import document_file_exists
    from clients.services.wniosek import build_submitted_document_summary

    from .zus import format_zus_months, missing_zus_months

    if case is None or getattr(case, "pk", None) is None:
        raise ValueError("build_case_document_checklist() requires a saved Case")

    client = case.client
    current_language = translation.get_language() or client.language
    purpose = purpose_for_case(case)

    if requirements_cache is not None:
        cache_key = f"case:{purpose}:{current_language}"
        if cache_key not in requirements_cache:
            required_docs = DocumentRequirement.required_for(purpose, current_language)
            reqs = list(DocumentRequirement.objects.filter(application_purpose=purpose))
            requirements_cache[cache_key] = (required_docs, reqs)
        required_docs, reqs = requirements_cache[cache_key]
    else:
        required_docs = DocumentRequirement.required_for(purpose, current_language)
        reqs = list(DocumentRequirement.objects.filter(application_purpose=purpose))

    prefetched_documents = getattr(client, "_prefetched_objects_cache", {}).get("documents")

    uploaded_docs: list[Document] | models.QuerySet[Document]
    if prefetched_documents is None:
        uploaded_docs = (
            client.documents.filter(case_id=case.pk)
            .annotate(preloaded_version_count=models.Count("versions"))
            .order_by("-uploaded_at")
        )
    else:
        uploaded_docs = sorted(
            [doc for doc in prefetched_documents if doc.case_id == case.pk],
            key=lambda document: document.uploaded_at,
            reverse=True,
        )

    req_map = {requirement.document_type: requirement for requirement in reqs}
    docs_map: dict[str, list[Document]] = {}
    for doc in uploaded_docs:
        setattr(doc, "_preloaded_version_count", getattr(doc, "preloaded_version_count", 0))
        setattr(doc, "_preloaded_requirement", req_map.get(doc.document_type))
        if check_file_existence:
            setattr(doc, "file_exists", document_file_exists(doc))
        docs_map.setdefault(doc.document_type, []).append(doc)

    submitted_summary = build_submitted_document_summary(client, case=case)
    submitted_by_code = submitted_summary.get("codes", {})
    custom_submissions = submitted_summary.get("custom", [])

    status_list: list[dict[str, Any]] = []
    seen_codes = set()

    def has_valid_document(documents: list[Document]) -> bool:
        return any(
            doc.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(doc, "file_exists", False))
            for doc in documents
        )

    for code, name in required_docs:
        documents = docs_map.get(code, [])
        submitted_records = submitted_by_code.get(code, [])
        status_list.append(
            {
                "code": code,
                "name": str(name),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document(documents) or bool(submitted_records),
                "documents": documents,
                "submitted_records": submitted_records,
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    for code, submitted_records in submitted_by_code.items():
        if code in seen_codes:
            continue
        documents = docs_map.get(code, [])
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document(documents) or bool(submitted_records),
                "documents": documents,
                "submitted_records": submitted_records,
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    for code, documents in docs_map.items():
        if code in seen_codes:
            continue
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document(documents),
                "documents": documents,
                "submitted_records": [],
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    prefetched_requirements = getattr(client, "_prefetched_objects_cache", {}).get("custom_document_requirements")
    custom_requirements: list[ClientDocumentRequirement] | models.QuerySet[ClientDocumentRequirement]
    if prefetched_requirements is None:
        custom_requirements = client.custom_document_requirements.filter(is_active=True).order_by("due_date", "created_at")
    else:
        custom_requirements = sorted(
            [requirement for requirement in prefetched_requirements if requirement.is_active],
            key=lambda requirement: (requirement.due_date or date.max, requirement.created_at),
        )

    for requirement in custom_requirements:
        documents = [
            document
            for document in docs_map.get(requirement.document_type, [])
            if getattr(document, "archived_at", None) is None
        ]
        status_list.append(
            {
                "code": requirement.document_type,
                "name": requirement.name,
                "description": requirement.description,
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document(documents) or not requirement.is_required,
                "documents": documents,
                "submitted_records": [],
                "is_custom_submission": False,
                "is_custom_requirement": True,
                "custom_requirement": requirement,
                "due_date": requirement.due_date,
                "is_required": requirement.is_required,
            }
        )

    for index, custom_item in enumerate(custom_submissions):
        status_list.append(
            {
                "code": f"submitted-custom-{index}",
                "name": str(custom_item["name"]),
                "is_uploaded": False,
                "is_submitted": True,
                "is_complete": True,
                "documents": [],
                "submitted_records": custom_item.get("records", []),
                "is_custom_submission": True,
            }
        )

    zus_missing: list[Any] = []
    zus_code = ""
    try:
        zus_code = DocumentType.ZUS_RCA_OR_INSURANCE.value
        zus_missing = list(missing_zus_months(case))
    except Exception:
        zus_missing = []

    for row in status_list:
        active_docs = [doc for doc in row.get("documents", []) if getattr(doc, "archived_at", None) is None]
        ocr_doc = next(
            (doc for doc in active_docs if getattr(doc, "awaiting_confirmation", False) or doc.ocr_status == "failed"),
            None,
        )
        verify_doc = next(
            (
                doc
                for doc in active_docs
                if doc.computed_status == "pending_review" and not getattr(doc, "awaiting_confirmation", False)
            ),
            None,
        )
        row["has_ocr_review"] = ocr_doc is not None
        row["needs_verification"] = verify_doc is not None
        row["ocr_review_doc_id"] = ocr_doc.id if ocr_doc is not None else None
        row["verification_doc_id"] = verify_doc.id if verify_doc is not None else None
        row["zus_missing_count"] = 0
        if zus_missing and zus_code and row.get("code") == zus_code:
            row["is_complete"] = False
            row["zus_missing_months"] = zus_missing
            row["zus_missing_count"] = len(zus_missing)
            row["zus_missing_label"] = format_zus_months(zus_missing)

    return status_list

def purpose_context_for_case(case: Any, mos_data: Any | None = None) -> dict[str, str | bool]:
    effective_purpose = purpose_for_case(case)
    client_selected_purpose = str(getattr(mos_data, "mos_purpose", "") or "") if mos_data else ""
    original_case_purpose = str(getattr(case, "application_purpose", "") or "")
    return {
        "effective_purpose": effective_purpose,
        "client_selected_purpose": client_selected_purpose,
        "original_case_purpose": original_case_purpose,
        "original_client_purpose": original_case_purpose,
        "effective_purpose_label": purpose_label(effective_purpose),
        "client_selected_purpose_label": purpose_label(client_selected_purpose),
        "original_case_purpose_label": purpose_label(original_case_purpose or effective_purpose),
        "original_client_purpose_label": purpose_label(original_case_purpose or effective_purpose),
        "purpose_mismatch": bool(client_selected_purpose and client_selected_purpose != effective_purpose),
    }
