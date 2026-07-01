from __future__ import annotations

from typing import Any

from django.utils import translation

from clients.models import DocumentRequirement
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

    This is the Case-first entry point for process screens. It delegates row
    construction to the legacy client method for now, but the purpose and
    documents are both scoped to ``case``.
    """

    return case.client.get_document_checklist(
        check_file_existence=check_file_existence,
        requirements_cache=requirements_cache,
        case=case,
    )


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
        "original_client_purpose_label": purpose_label(original_case_purpose or effective_purpose),
        "purpose_mismatch": bool(client_selected_purpose and client_selected_purpose != effective_purpose),
    }
