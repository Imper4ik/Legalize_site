from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _

from clients.models import Client, ClientOnboardingSession, Document, DocumentRequirement, MOSApplicationData
from clients.views.onboarding_views import (
    _document_source_hint,
    _locked_response,
    _mos_data_is_editable,
    _purpose_context,
    _sync_contact_fields_to_client,
    check_onboarding_session,
)

CONTACT_REQUIRED_FIELDS = ("first_name", "last_name", "email", "phone")
START_TEMPLATE = "clients/onboarding/start_contact.html"


def _contact_values_from_client(client: Client, mos_data: MOSApplicationData | None) -> dict[str, str]:
    personal_data = mos_data.personal_data if mos_data and isinstance(mos_data.personal_data, dict) else {}
    return {
        "first_name": str(client.first_name or personal_data.get("first_name") or "").strip(),
        "last_name": str(client.last_name or personal_data.get("last_name") or "").strip(),
        "email": str(client.email or personal_data.get("email") or "").strip(),
        "phone": str(client.phone or personal_data.get("phone") or "").strip(),
    }


def _contact_values_from_post(request: HttpRequest) -> dict[str, str]:
    return {
        "first_name": request.POST.get("first_name", "").strip(),
        "last_name": request.POST.get("last_name", "").strip(),
        "email": request.POST.get("email", "").strip().lower(),
        "phone": request.POST.get("phone", "").strip(),
    }


def _validate_contact_values(values: dict[str, str]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not values.get("first_name"):
        errors["first_name"] = str(_("Укажите имя."))
    if not values.get("last_name"):
        errors["last_name"] = str(_("Укажите фамилию."))
    if not values.get("email"):
        errors["email"] = str(_("Укажите email."))
    else:
        try:
            validate_email(values["email"])
        except ValidationError:
            errors["email"] = str(_("Введите корректный email."))
    if not values.get("phone"):
        errors["phone"] = str(_("Укажите телефон."))
    elif len(values["phone"]) < 6:
        errors["phone"] = str(_("Телефон должен содержать минимум 6 символов."))
    return errors


def _save_contact_values(client: Client, mos_data: MOSApplicationData, values: dict[str, str]) -> None:
    _sync_contact_fields_to_client(client, **values)

    personal_data = dict(mos_data.personal_data or {})
    for field_name in CONTACT_REQUIRED_FIELDS:
        personal_data[field_name] = values[field_name]
    mos_data.personal_data = personal_data

    update_fields = ["personal_data", "updated_at"]
    if mos_data.status == "draft":
        mos_data.status = "client_filling"
        update_fields.append("status")
    mos_data.save(update_fields=update_fields)


def _case_step_for_status(status: str) -> int:
    if status in ["draft", "client_filling", "client_completed", "needs_correction"]:
        return 1
    if status in ["staff_review"]:
        return 2
    if status in ["approved_by_staff", "mos_package_ready"]:
        return 3
    if status in ["submitted_in_mos"]:
        return 4
    if status in ["fingerprints"]:
        return 5
    if status in ["waiting_decision", "decision_received", "closed"]:
        return 6
    return 1


def _build_start_context(
    *,
    session: ClientOnboardingSession,
    contact_values: dict[str, str] | None = None,
    contact_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    client = session.client
    mos_data, _ = MOSApplicationData.objects.get_or_create(client=client)
    purpose_ctx = _purpose_context(client, mos_data)
    effective_purpose = str(purpose_ctx["effective_purpose"])
    language = translation.get_language() or client.language
    required_docs_catalog = DocumentRequirement.catalog_for(purpose=effective_purpose, language=language)

    existing_documents = list(Document.objects.filter(client=client).order_by("document_type", "-uploaded_at"))
    existing_map = {document.document_type: document.id for document in existing_documents}

    checklist = []
    checklist_codes = set()
    for item in required_docs_catalog:
        doc_type = item["code"]
        checklist_codes.add(doc_type)
        checklist.append({
            "code": doc_type,
            "label": item["label"],
            "is_required": item["is_required"],
            "is_uploaded": doc_type in existing_map,
            "doc_id": existing_map.get(doc_type),
            "source_hint": _document_source_hint(doc_type),
        })

    additional_documents = [
        {
            "id": document.id,
            "code": document.document_type,
            "label": document.display_name,
            "source_hint": _document_source_hint(document.document_type),
        }
        for document in existing_documents
        if document.document_type not in checklist_codes
    ]

    contact_values = contact_values or _contact_values_from_client(client, mos_data)
    contact_complete = all(contact_values.get(field_name) for field_name in CONTACT_REQUIRED_FIELDS)
    allow_edit = _mos_data_is_editable(mos_data)

    return {
        "session": session,
        "mos_data": mos_data,
        "checklist": checklist,
        "allow_edit": allow_edit,
        "allow_delete": bool(mos_data and allow_edit),
        "case_step": _case_step_for_status(mos_data.status if mos_data else "draft"),
        "additional_documents": additional_documents,
        "can_change_purpose": allow_edit,
        "contact_values": contact_values,
        "contact_errors": contact_errors or {},
        "contact_complete": contact_complete,
        **purpose_ctx,
    }


def onboarding_start_contact(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    client = session.client
    mos_data, _ = MOSApplicationData.objects.get_or_create(client=client)

    if request.method == "POST":
        if not _mos_data_is_editable(mos_data):
            return _locked_response(request, session)

        contact_values = _contact_values_from_post(request)
        contact_errors = _validate_contact_values(contact_values)
        if contact_errors:
            return render(
                request,
                START_TEMPLATE,
                _build_start_context(
                    session=session,
                    contact_values=contact_values,
                    contact_errors=contact_errors,
                ),
            )

        _save_contact_values(client, mos_data, contact_values)
        return redirect("clients:onboarding_purpose", token=token)

    return render(request, START_TEMPLATE, _build_start_context(session=session))
