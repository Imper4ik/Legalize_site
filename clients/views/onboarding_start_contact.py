from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Client, ClientOnboardingSession, Document, DocumentRequirement, MOSApplicationData
from clients.views.onboarding_views import (
    _document_source_hint,
    _locked_response,
    _mos_data_is_editable,
    _mos_documents_are_editable,
    _purpose_context,
    _sync_contact_fields_to_client,
    check_onboarding_session,
    check_client_auth,
)

CONTACT_REQUIRED_FIELDS = ("first_name", "last_name", "email", "phone")
CONTACT_PLACEHOLDER_PAIRS = {("новый", "клиент"), ("new", "client")}
START_TEMPLATE = "clients/onboarding/start_contact.html"


def _clean_placeholder_contact_value(field_name: str, value: str, *, first_name: str, last_name: str) -> str:
    if (first_name.strip().lower(), last_name.strip().lower()) in CONTACT_PLACEHOLDER_PAIRS:
        if field_name in {"first_name", "last_name"}:
            return ""
    return value.strip()


def _contact_values_from_client(client: Client, mos_data: MOSApplicationData | None) -> dict[str, str]:
    personal_data = mos_data.personal_data if mos_data and isinstance(mos_data.personal_data, dict) else {}
    raw_first_name = str(client.first_name or personal_data.get("first_name") or "").strip()
    raw_last_name = str(client.last_name or personal_data.get("last_name") or "").strip()
    return {
        "first_name": _clean_placeholder_contact_value("first_name", raw_first_name, first_name=raw_first_name, last_name=raw_last_name),
        "last_name": _clean_placeholder_contact_value("last_name", raw_last_name, first_name=raw_first_name, last_name=raw_last_name),
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


def _contact_is_complete(values: dict[str, str]) -> bool:
    return all(values.get(field_name) for field_name in CONTACT_REQUIRED_FIELDS)


def _contact_form_is_editable(mos_data: MOSApplicationData | None, contact_values: dict[str, str]) -> bool:
    return _mos_data_is_editable(mos_data) or not _contact_is_complete(contact_values)


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
    try:
        mos_data = MOSApplicationData.objects.get(client=client)
    except MOSApplicationData.DoesNotExist:
        mos_data = MOSApplicationData(client=client)
    purpose_ctx = _purpose_context(client, mos_data)
    effective_purpose = str(purpose_ctx["effective_purpose"])
    language = translation.get_language() or client.language

    fingerprint_invitation_doc_type = DocumentType.WEZWANIE.value
    existing_documents = list(Document.objects.filter(client=client).order_by("document_type", "-uploaded_at"))
    existing_map = {document.document_type: document.id for document in existing_documents}

    required_docs_catalog = DocumentRequirement.catalog_for(purpose=effective_purpose, language=language)

    import os
    from django.conf import settings

    checklist = []
    checklist_codes = set()
    for item in required_docs_catalog:
        doc_type = item["code"]
        checklist_codes.add(doc_type)
        is_uploaded = doc_type in existing_map
        
        doc_obj = next((d for d in existing_documents if d.document_type == doc_type), None)
        
        sample_image_url = item.get("sample_image_url")
        if not sample_image_url:
            static_filename = f"clients/images/samples/{doc_type}.png"
            static_filepath = os.path.join(settings.BASE_DIR, "static", static_filename)
            if os.path.exists(static_filepath):
                sample_image_url = settings.STATIC_URL + static_filename

        checklist.append({
            "code": doc_type,
            "label": item["label"],
            "is_required": item["is_required"],
            "is_uploaded": is_uploaded,
            "doc_id": doc_obj.id if doc_obj else None,
            "ocr_status": doc_obj.ocr_status if doc_obj else None,
            "ocr_status_badge": doc_obj.ocr_status_badge if doc_obj else "",
            "source_hint": _document_source_hint(doc_type),
            "sample_image_url": sample_image_url,
        })

    fingerprint_invitation_document = next(
        (document for document in existing_documents if document.document_type == fingerprint_invitation_doc_type),
        None,
    )

    fingerprint_invitation_sample_url = None
    static_wezwanie_filename = "clients/images/samples/wezwanie.png"
    static_wezwanie_filepath = os.path.join(settings.BASE_DIR, "static", static_wezwanie_filename)
    if os.path.exists(static_wezwanie_filepath):
        fingerprint_invitation_sample_url = settings.STATIC_URL + static_wezwanie_filename

    additional_documents = [
        {
            "id": document.id,
            "code": document.document_type,
            "label": document.display_name,
            "source_hint": _document_source_hint(document.document_type),
        }
        for document in existing_documents
        if document.document_type not in checklist_codes and document.document_type != fingerprint_invitation_doc_type
    ]

    contact_values = contact_values or _contact_values_from_client(client, mos_data)
    contact_complete = _contact_is_complete(contact_values)
    allow_edit = _mos_data_is_editable(mos_data)
    contact_form_editable = _contact_form_is_editable(mos_data, contact_values)
    allow_doc_edit = _mos_documents_are_editable(mos_data)
    docs_total_count = len(checklist)
    docs_uploaded_count = sum(1 for doc in checklist if doc["is_uploaded"])
    docs_required_pending_count = sum(1 for doc in checklist if doc["is_required"] and not doc["is_uploaded"])

    status_completed = mos_data is not None and mos_data.status in {
        "client_completed",
        "mos_package_ready",
        "submitted_in_mos",
        "approved_by_staff",
    }
    passport_complete = status_completed or bool(
        mos_data
        and isinstance(mos_data.passport_data, dict)
        and mos_data.passport_data.get("document_number")
        and isinstance(mos_data.address_data, dict)
        and mos_data.address_data.get("city")
    )
    travel_complete = status_completed or bool(
        mos_data
        and isinstance(mos_data.stay_data, dict)
        and mos_data.stay_data.get("stay_basis")
    )

    case_step = _case_step_for_status(mos_data.status if mos_data else "draft")

    return {
        "session": session,
        "mos_data": mos_data,
        "checklist": checklist,
        "allow_edit": allow_edit,
        "contact_form_editable": contact_form_editable,
        "allow_doc_edit": allow_doc_edit,
        "allow_delete": bool(mos_data and allow_doc_edit),
        "case_step": case_step,
        "is_post_fingerprints": case_step >= 5,
        "additional_documents": additional_documents,
        "fingerprint_invitation_doc_type": fingerprint_invitation_doc_type,
        "fingerprint_invitation_document": fingerprint_invitation_document,
        "fingerprint_invitation_label": client.get_document_name_by_code(fingerprint_invitation_doc_type),
        "fingerprint_invitation_sample_url": fingerprint_invitation_sample_url,
        "can_change_purpose": allow_edit,
        "contact_values": contact_values,
        "contact_errors": contact_errors or {},
        "contact_complete": contact_complete,
        "docs_total_count": docs_total_count,
        "docs_uploaded_count": docs_uploaded_count,
        "docs_required_pending_count": docs_required_pending_count,
        "passport_complete": passport_complete,
        "travel_complete": travel_complete,
        **purpose_ctx,
    }


def onboarding_start_contact(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect

    client = session.client
    try:
        mos_data = MOSApplicationData.objects.get(client=client)
    except MOSApplicationData.DoesNotExist:
        mos_data = MOSApplicationData(client=client)

    if request.method == "POST":
        mos_data, _created = MOSApplicationData.objects.get_or_create(client=client)
        existing_contact_values = _contact_values_from_client(client, mos_data)
        if not _contact_form_is_editable(mos_data, existing_contact_values):
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
        if not _mos_data_is_editable(mos_data):
            return redirect("clients:onboarding_start", token=token)
        return redirect("clients:onboarding_digital_access", token=token)

    return render(request, START_TEMPLATE, _build_start_context(session=session))
