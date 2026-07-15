from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import translation

if TYPE_CHECKING:
    from clients.models import Client, ClientDocumentRequirement, Document

def build_document_checklist(
    client: "Client",
    check_file_existence: bool = False,
    requirements_cache: dict[str, Any] | None = None,
    case: Any = None,
) -> list[dict[str, Any]]:
    """Build the required-document checklist.

    When ``case`` is provided the uploaded documents are scoped to that case
    so multi-case clients are not cross-contaminated (case-first). Without a
    case the legacy client-wide view is returned for backward compatibility.
    """
    if case is not None:
        from clients.services.case_context import build_case_document_checklist

        return build_case_document_checklist(
            case,
            check_file_existence=check_file_existence,
            requirements_cache=requirements_cache,
        )

    from clients.services.document_helpers import document_file_exists

    from .document import DocumentRequirement, resolve_document_label

    current_language = translation.get_language() or client.language
    if case is not None:
        from clients.services.case_context import purpose_for_case

        purpose = purpose_for_case(case)
    else:
        purpose = client.get_document_requirement_purpose()

    if requirements_cache is not None:
        cache_key = f"{purpose}:{current_language}"
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
        documents_qs = client.documents.all()
        uploaded_docs = documents_qs.annotate(
            preloaded_version_count=models.Count("versions")
        ).order_by("-uploaded_at")
    else:
        uploaded_docs = sorted(
            prefetched_documents,
            key=lambda document: document.uploaded_at,
            reverse=True,
        )

    req_map = {r.document_type: r for r in reqs}

    docs_map: dict[str, list[Document]] = {}
    for doc in uploaded_docs:
        setattr(doc, "_preloaded_version_count", getattr(doc, "preloaded_version_count", 0))
        setattr(doc, "_preloaded_requirement", req_map.get(doc.document_type))
        if check_file_existence:
            setattr(doc, "file_exists", document_file_exists(doc))
        docs_map.setdefault(doc.document_type, []).append(doc)

    # Scope Wniosek submissions to the same case as the documents so a
    # submission from another case cannot complete this case's checklist
    # (spec §7).
    submitted_summary = client.get_submitted_document_summary()
    submitted_by_code = submitted_summary.get("codes", {})
    custom_submissions = submitted_summary.get("custom", [])

    status_list: list[dict[str, Any]] = []
    seen_codes = set()
    for code, name in required_docs:
        documents = docs_map.get(code, [])
        submitted_records = submitted_by_code.get(code, [])
        has_valid_document = any(
            doc.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(doc, "file_exists", False))
            for doc in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(name),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document or bool(submitted_records),
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
        has_valid_document = any(
            doc.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(doc, "file_exists", False))
            for doc in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": bool(submitted_records),
                "is_complete": has_valid_document or bool(submitted_records),
                "documents": documents,
                "submitted_records": submitted_records,
                "is_custom_submission": False,
            }
        )
        seen_codes.add(code)

    for code, documents in docs_map.items():
        if code in seen_codes:
            continue
        has_valid_document = any(
            doc.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(doc, "file_exists", False))
            for doc in documents
        )
        status_list.append(
            {
                "code": code,
                "name": str(resolve_document_label(code, language=current_language)),
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document,
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
        has_valid_document = any(
            doc.computed_status in ("approved", "pending_review")
            and (not check_file_existence or getattr(doc, "file_exists", False))
            for doc in documents
        )
        status_list.append(
            {
                "code": requirement.document_type,
                "name": requirement.name,
                "description": requirement.description,
                "is_uploaded": bool(documents),
                "is_submitted": False,
                "is_complete": has_valid_document or not requirement.is_required,
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

    # ZUS RCA completeness is per-month, not "any upload": a client in
    # waiting_decision needs a ZUS RCA for every required month, so the row
    # must stay incomplete while a month is missing even if some files exist.
    zus_missing: list[Any] = []
    zus_code = ""
    try:
        from clients.constants import DocumentType
        from clients.services.zus import missing_zus_months

        zus_code = DocumentType.ZUS_RCA_OR_INSURANCE.value
        from clients.services.cases import resolve_single_active_case
        zus_subject = resolve_single_active_case(client)
        if zus_subject is not None:
            zus_missing = list(missing_zus_months(zus_subject))
    except Exception:
        zus_missing = []

    # Flag, per checklist row, which uploaded documents need staff attention
    # so the collapsed list distinguishes an OCR review from a plain manual
    # verification (one badge each, never double-counting the same file).
    for row in status_list:
        active_docs = [
            doc for doc in row.get("documents", [])
            if getattr(doc, "archived_at", None) is None
        ]
        ocr_doc = next(
            (doc for doc in active_docs
             if getattr(doc, "awaiting_confirmation", False) or doc.ocr_status == "failed"),
            None,
        )
        verify_doc = next(
            (doc for doc in active_docs
             if doc.computed_status == "pending_review"
             and not getattr(doc, "awaiting_confirmation", False)),
            None,
        )
        warning_doc = next(
            (
                doc
                for doc in active_docs
                if not getattr(doc, "awaiting_confirmation", False)
                and doc.ocr_status != "failed"
                and (
                    getattr(doc, "ocr_name_mismatch", False)
                    or bool((getattr(doc, "parsed_data", None) or {}).get("warnings"))
                )
            ),
            None,
        )
        row["has_ocr_review"] = ocr_doc is not None
        row["needs_verification"] = verify_doc is not None
        row["has_ocr_warning"] = warning_doc is not None
        # The exact document a status badge should jump to ("веди на проблему").
        row["ocr_review_doc_id"] = ocr_doc.id if ocr_doc is not None else None
        row["verification_doc_id"] = verify_doc.id if verify_doc is not None else None
        row["ocr_warning_doc_id"] = warning_doc.id if warning_doc is not None else None

        # ZUS RCA: a missing required month keeps the row incomplete (not green)
        # even when some months are already uploaded.
        row["zus_missing_count"] = 0
        if zus_missing and zus_code and row.get("code") == zus_code:
            from clients.services.zus import format_zus_months

            row["is_complete"] = False
            row["zus_missing_months"] = zus_missing
            row["zus_missing_count"] = len(zus_missing)
            row["zus_missing_label"] = format_zus_months(zus_missing)

    return status_list
