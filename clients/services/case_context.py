from __future__ import annotations

from datetime import date
from typing import Any

from django.db import models
from django.utils import translation

from clients.models import DocumentRequirement
from clients.services.onboarding_purposes import ALLOWED_ONBOARDING_PURPOSES, purpose_label


def purpose_for_case(case: Any) -> str:
    """Return the document-requirement purpose for a concrete Case.

    Case is the sole owner of the process purpose (spec §4): new clients get it
    copied onto their first case at creation, legacy single-case rows were
    backfilled by migration 0122, and a case without a purpose deliberately
    yields "" so callers force an explicit purpose selection instead of
    borrowing one from the client or a sibling case.
    """

    case_purpose = str(getattr(case, "application_purpose", "") or "").strip()
    if case_purpose:
        family_role = str(getattr(case, "family_role", "") or "").strip()
        if case_purpose == "family" and family_role and family_role != "sponsor":
            return family_role
        if case_purpose == "family" and family_role == "sponsor":
            return "work"
        return case_purpose
    return ""


def working_purpose_for_case(case: Any, mos_data: Any | None = None) -> str:
    """Purpose that drives the client portal for one Case.

    The Case purpose is authoritative once staff set it. Until then the
    client's own questionnaire selection (``mos_purpose``) drives their
    checklist, so a second case never silently borrows another case's
    purpose and the client is not shown an empty "all collected" list.
    """

    purpose = purpose_for_case(case)
    if purpose:
        return purpose
    selected = str(getattr(mos_data, "mos_purpose", "") or "").strip()
    if selected in ALLOWED_ONBOARDING_PURPOSES:
        return selected
    return ""


def checklist_for_case(
    case: Any,
    language: str | None = None,
    *,
    include_optional: bool = True,
    include_fallback: bool = True,
    purpose: str | None = None,
) -> list[dict[str, Any]]:
    """Return document requirements for the selected Case only."""

    if purpose is None:
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

    This is the canonical Case-first checklist builder.  It deliberately scopes
    documents, Wniosek submissions, custom requirements and ZUS completeness to
    the supplied case so another case of the same client can never make this
    checklist look complete.
    """

    from clients.constants import DocumentType
    from clients.models.document import ClientDocumentRequirement, Document, resolve_document_label
    from clients.services.document_helpers import document_file_exists, document_has_ocr_warning
    from clients.services.zus import format_zus_months, missing_zus_months

    client = case.client
    case_id = getattr(case, "pk", None)
    current_language = translation.get_language() or client.language
    purpose = purpose_for_case(case)

    if requirements_cache is not None:
        cache_key = f"{purpose}:{current_language}"
        if cache_key not in requirements_cache:
            required_docs = DocumentRequirement.required_for(purpose, current_language)
            requirements = list(DocumentRequirement.objects.filter(application_purpose=purpose))
            requirements_cache[cache_key] = (required_docs, requirements)
        required_docs, requirements = requirements_cache[cache_key]
    else:
        required_docs = DocumentRequirement.required_for(purpose, current_language)
        requirements = list(DocumentRequirement.objects.filter(application_purpose=purpose))

    prefetched_documents = getattr(case, "_prefetched_objects_cache", {}).get("documents")
    uploaded_docs: list[Document] | models.QuerySet[Document]
    if prefetched_documents is None:
        uploaded_docs = case.documents.all().annotate(
            preloaded_version_count=models.Count("versions")
        ).order_by("-uploaded_at")
    else:
        uploaded_docs = sorted(
            [document for document in prefetched_documents if document.case_id == case_id],
            key=lambda document: document.uploaded_at,
            reverse=True,
        )

    requirement_map = {requirement.document_type: requirement for requirement in requirements}
    documents_by_code: dict[str, list[Document]] = {}
    for document in uploaded_docs:
        setattr(document, "_preloaded_version_count", getattr(document, "preloaded_version_count", 0))
        setattr(document, "_preloaded_requirement", requirement_map.get(document.document_type))
        if check_file_existence:
            setattr(document, "file_exists", document_file_exists(document))
        documents_by_code.setdefault(document.document_type, []).append(document)

    submitted_summary = client.get_submitted_document_summary(case=case)
    submitted_by_code = submitted_summary.get("codes", {})
    custom_submissions = submitted_summary.get("custom", [])

    status_list: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for code, name in required_docs:
        documents = documents_by_code.get(code, [])
        submitted_records = submitted_by_code.get(code, [])
        has_valid_document = any(
            document.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(document, "file_exists", False))
            for document in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(name),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document or bool(submitted_records),
                "is_required": True,
                "documents": documents,
                "submitted_records": submitted_records,
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    for code, submitted_records in submitted_by_code.items():
        if code in seen_codes:
            continue
        documents = documents_by_code.get(code, [])
        has_valid_document = any(
            document.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(document, "file_exists", False))
            for document in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document or bool(submitted_records),
                "is_required": False,
                "documents": documents,
                "submitted_records": submitted_records,
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    for code, documents in documents_by_code.items():
        if code in seen_codes:
            continue
        has_valid_document = any(
            document.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(document, "file_exists", False))
            for document in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document,
                "is_required": False,
                "documents": documents,
                "submitted_records": [],
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    prefetched_requirements = getattr(case, "_prefetched_objects_cache", {}).get("custom_document_requirements")
    custom_requirements: list[ClientDocumentRequirement] | models.QuerySet[ClientDocumentRequirement]
    if prefetched_requirements is None:
        custom_requirements = ClientDocumentRequirement.objects.filter(
            client=client,
            case=case,
            is_active=True,
        ).order_by("due_date", "created_at")
    else:
        custom_requirements = sorted(
            [
                requirement
                for requirement in prefetched_requirements
                if requirement.case_id == case_id and requirement.is_active
            ],
            key=lambda requirement: (requirement.due_date or date.max, requirement.created_at),
        )

    for requirement in custom_requirements:
        documents = [
            document
            for document in documents_by_code.get(requirement.document_type, [])
            if getattr(document, "archived_at", None) is None
        ]
        has_valid_document = any(
            document.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(document, "file_exists", False))
            for document in documents
        )
        status_list.append(
            {
                "code": requirement.document_type,
                "name": requirement.name,
                "description": requirement.description,
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document or not requirement.is_required,
                "is_required": requirement.is_required,
                "documents": documents,
                "submitted_records": [],
                "is_custom_submission": False,
                "is_custom_requirement": True,
                "custom_requirement": requirement,
                "due_date": requirement.due_date,
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
                "is_required": False,
                "documents": [],
                "submitted_records": custom_item.get("records", []),
                "is_custom_submission": True,
            }
        )

    zus_code = DocumentType.ZUS_RCA_OR_INSURANCE.value
    try:
        zus_missing = list(missing_zus_months(case))
    except Exception:
        zus_missing = []

    for row in status_list:
        active_documents = [
            document
            for document in row.get("documents", [])
            if getattr(document, "archived_at", None) is None
        ]
        ocr_document = next(
            (
                document
                for document in active_documents
                if getattr(document, "awaiting_confirmation", False) or document.ocr_status == "failed"
            ),
            None,
        )
        verification_document = next(
            (
                document
                for document in active_documents
                if document.computed_status == "pending_review"
                and not getattr(document, "awaiting_confirmation", False)
            ),
            None,
        )
        warning_document = next(
            (
                document
                for document in active_documents
                if not getattr(document, "awaiting_confirmation", False)
                and document.ocr_status != "failed"
                and document_has_ocr_warning(document)
            ),
            None,
        )
        row["has_ocr_review"] = ocr_document is not None
        row["needs_verification"] = verification_document is not None
        row["has_ocr_warning"] = warning_document is not None
        row["ocr_review_doc_id"] = ocr_document.id if ocr_document is not None else None
        row["verification_doc_id"] = verification_document.id if verification_document is not None else None
        row["ocr_warning_doc_id"] = warning_document.id if warning_document is not None else None
        row["zus_missing_count"] = 0
        if zus_missing and row.get("code") == zus_code:
            row["is_complete"] = False
            row["zus_missing_months"] = zus_missing
            row["zus_missing_count"] = len(zus_missing)
            row["zus_missing_label"] = format_zus_months(zus_missing)

    return status_list


def purpose_context_for_case(case: Any, mos_data: Any | None = None) -> dict[str, str | bool]:
    case_purpose = purpose_for_case(case)
    effective_purpose = working_purpose_for_case(case, mos_data)
    client_selected_purpose = str(getattr(mos_data, "mos_purpose", "") or "") if mos_data else ""
    original_case_purpose = str(getattr(case, "application_purpose", "") or "")
    return {
        "effective_purpose": effective_purpose,
        "client_selected_purpose": client_selected_purpose,
        "original_case_purpose": original_case_purpose,
        "effective_purpose_label": purpose_label(effective_purpose),
        "client_selected_purpose_label": purpose_label(client_selected_purpose),
        "original_case_purpose_label": purpose_label(original_case_purpose or effective_purpose),
        # A mismatch exists only against a purpose staff actually set on the
        # case; a not-yet-applied client selection is the working purpose, not
        # a conflict (staff review still confirms it before submission).
        "purpose_mismatch": bool(
            client_selected_purpose and case_purpose and client_selected_purpose != case_purpose
        ),
    }
