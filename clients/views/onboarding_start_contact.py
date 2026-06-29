from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone, translation
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, ClientOnboardingSession, Document, DocumentRequirement, MOSApplicationData
from clients.services.document_workflow import upload_client_document
from clients.views.onboarding_views import (
    _document_source_hint,
    _ensure_mos,
    _locked_response,
    _mos_data_is_editable,
    _mos_documents_are_editable,
    _purpose_context,
    _require_portal_case,
    _session_case,
    _sync_contact_fields_to_client,
    check_client_auth,
    check_onboarding_session,
)

CONTACT_REQUIRED_FIELDS = ("first_name", "last_name", "email", "phone")
CONTACT_PLACEHOLDER_PAIRS = {("новый", "клиент"), ("new", "client")}
START_TEMPLATE = "clients/onboarding/start_contact.html"
NEW_CARD_CONFIRMATION_DOC_TYPE = DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value
NEW_CARD_STATUS_YES = MOSApplicationData.NEW_CARD_STATUS_YES
NEW_CARD_STATUS_NO = MOSApplicationData.NEW_CARD_STATUS_NO
NEW_CARD_STATUS_UNKNOWN = MOSApplicationData.NEW_CARD_STATUS_UNKNOWN
NEW_CARD_STATUS_SUBMITTED_NO_NUMBER = "submitted_no_number"
NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER = "submitted_with_number"

NEW_CARD_ALLOWED_STATUSES = {
    NEW_CARD_STATUS_NO,
    NEW_CARD_STATUS_SUBMITTED_NO_NUMBER,
    NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER,
    NEW_CARD_STATUS_UNKNOWN,
}
NEW_CARD_CONFIRMATION_UPLOAD_STATUSES = {
    NEW_CARD_STATUS_SUBMITTED_NO_NUMBER,
    NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER,
    NEW_CARD_STATUS_UNKNOWN,
}


def _clean_placeholder_contact_value(field_name: str, value: str, *, first_name: str, last_name: str) -> str:
    if (first_name.strip().lower(), last_name.strip().lower()) in CONTACT_PLACEHOLDER_PAIRS:
        if field_name in {"first_name", "last_name"}:
            return ""
    return value.strip()


def _contact_values_from_client(client: Client, mos_data: MOSApplicationData | None) -> dict[str, str]:
    personal_data: dict[str, Any] = (
        cast("dict[str, Any]", mos_data.personal_data)
        if mos_data and isinstance(mos_data.personal_data, dict)
        else {}
    )
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

    personal_data = dict(cast("dict[str, Any]", mos_data.personal_data) or {})
    for field_name in CONTACT_REQUIRED_FIELDS:
        personal_data[field_name] = values[field_name]
    # EncryptedJSONField stores dicts but django-stubs types it as text.
    mos_data.personal_data = personal_data  # type: ignore[assignment]

    update_fields = ["personal_data", "updated_at"]
    if mos_data.status == "draft":
        mos_data.status = "client_filling"
        update_fields.append("status")
    mos_data.save(update_fields=update_fields)


def _latest_new_card_confirmation_document(client: Client, case: Any = None) -> Document | None:
    qs = Document.objects.filter(
        client=client,
        document_type=NEW_CARD_CONFIRMATION_DOC_TYPE,
        archived_at__isnull=True,
    )
    if case is not None:
        qs = qs.filter(case=case)
    return qs.order_by("-uploaded_at", "-id").first()


def _new_card_values_from_mos(mos_data: MOSApplicationData | None) -> dict[str, str]:
    if mos_data is None:
        return {
            "status": "",
            "case_number": "",
            "submitted_at": "",
            "comment": "",
        }
    status = mos_data.new_residence_card_application_status or ""
    if status == MOSApplicationData.NEW_CARD_STATUS_YES:
        if mos_data.new_residence_card_case_number:
            status = NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER
        else:
            status = NEW_CARD_STATUS_SUBMITTED_NO_NUMBER
    return {
        "status": status,
        "case_number": str(mos_data.new_residence_card_case_number or ""),
        "submitted_at": mos_data.new_residence_card_submitted_at.isoformat()
        if mos_data.new_residence_card_submitted_at
        else "",
        "comment": mos_data.new_residence_card_comment or "",
    }


def _new_card_values_from_post(request: HttpRequest) -> dict[str, str]:
    status = request.POST.get("new_card_application_status", "").strip()
    if status == MOSApplicationData.NEW_CARD_STATUS_YES:
        if request.POST.get("new_card_case_number", "").strip():
            status = NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER
        else:
            status = NEW_CARD_STATUS_SUBMITTED_NO_NUMBER
    return {
        "status": status,
        "case_number": request.POST.get("new_card_case_number", "").strip(),
        "submitted_at": request.POST.get("new_card_submitted_at", "").strip(),
        "comment": request.POST.get("new_card_comment", "").strip(),
    }


def _validate_new_card_values(values: dict[str, str]) -> dict[str, str]:
    errors: dict[str, str] = {}
    status = values.get("status", "")
    if status not in NEW_CARD_ALLOWED_STATUSES:
        errors["status"] = str(_("Wybierz odpowiedź / Выберите ответ."))

    submitted_at = values.get("submitted_at", "")
    if status in (NEW_CARD_STATUS_SUBMITTED_NO_NUMBER, NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER):
        parsed_submitted_at = parse_date(submitted_at) if submitted_at else None
        if submitted_at and parsed_submitted_at is None:
            errors["submitted_at"] = str(_("Podaj poprawną datę / Укажите корректную дату."))
        elif parsed_submitted_at and parsed_submitted_at > timezone.localdate():
            errors["submitted_at"] = str(_("Data złożenia nie może być w przyszłości. / Дата подачи не может быть в будущем."))
        if status == NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER:
            if not values.get("case_number", "").strip():
                errors["case_number"] = str(_("Podaj numer sprawy / Укажите номер дела."))
    return errors


def _save_new_card_values(mos_data: MOSApplicationData, values: dict[str, str]) -> None:
    status = values["status"]
    if status in (NEW_CARD_STATUS_SUBMITTED_NO_NUMBER, NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER):
        mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_YES
        mos_data.new_residence_card_case_number = values.get("case_number", "")
        submitted_at = values.get("submitted_at", "")
        mos_data.new_residence_card_submitted_at = parse_date(submitted_at) if submitted_at else None
    elif status == NEW_CARD_STATUS_NO:
        mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_NO
        mos_data.new_residence_card_case_number = ""
        mos_data.new_residence_card_submitted_at = None
    elif status == NEW_CARD_STATUS_UNKNOWN:
        mos_data.new_residence_card_application_status = MOSApplicationData.NEW_CARD_STATUS_UNKNOWN
        mos_data.new_residence_card_case_number = ""
        mos_data.new_residence_card_submitted_at = None
    mos_data.new_residence_card_comment = values.get("comment", "")
    mos_data.new_residence_card_updated_at = timezone.now()
    mos_data.save(
        update_fields=[
            "new_residence_card_application_status",
            "new_residence_card_case_number",
            "new_residence_card_submitted_at",
            "new_residence_card_comment",
            "new_residence_card_updated_at",
            "updated_at",
        ]
    )


def _new_card_missing_warnings(mos_data: MOSApplicationData, confirmation_document: Document | None) -> list[str]:
    if mos_data.new_residence_card_application_status == MOSApplicationData.NEW_CARD_STATUS_YES:
        warnings = []
        if not mos_data.new_residence_card_case_number:
            warnings.append(str(_("Prosimy o uzupełnienie numeru sprawy, jeśli jest już dostępny. / Пожалуйста, добавьте номер дела, если он уже доступен.")))
        if not confirmation_document:
            warnings.append(str(_("Prosimy o załadowanie potwierdzenia złożenia wniosku o kartę pobytu. / Пожалуйста, загрузите подтверждение подачи заявления на карту пребывания.")))
        if not mos_data.new_residence_card_submitted_at:
            warnings.append(str(_("Jeśli znasz datę złożenia wniosku, dodaj ją w tym bloku. / Если знаете дату подачи заявления, добавьте её в этом блоке.")))
        return warnings
    if mos_data.new_residence_card_application_status == MOSApplicationData.NEW_CARD_STATUS_UNKNOWN:
        return [
            str(_("Prosimy o sprawdzenie, czy posiada Pan/Pani potwierdzenie złożenia wniosku, pieczątkę w paszporcie lub wiadomość z urzędu. / Пожалуйста, проверьте, есть ли у вас подтверждение подачи заявления, печать в паспорте или сообщение из управления (urząd)."))
        ]
    return []


def _handle_new_card_application_post(
    request: HttpRequest,
    *,
    session: ClientOnboardingSession,
    mos_data: MOSApplicationData,
    token: str,
) -> HttpResponse:
    if not _mos_documents_are_editable(mos_data):
        return _locked_response(request, session)

    values = _new_card_values_from_post(request)
    errors = _validate_new_card_values(values)
    upload_form: DocumentUploadForm | None = None
    confirmation_file = request.FILES.get("new_card_confirmation_file")
    if confirmation_file and values.get("status") in NEW_CARD_CONFIRMATION_UPLOAD_STATUSES:
        files_dict = request.FILES.copy()
        files_dict["file"] = confirmation_file
        upload_form = DocumentUploadForm(
            request.POST,
            files_dict,
            doc_type=NEW_CARD_CONFIRMATION_DOC_TYPE,
            client=session.client,
        )
        if not upload_form.is_valid():
            errors["confirmation_file"] = " ".join(
                str(error) for field_errors in upload_form.errors.values() for error in field_errors
            )

    if errors:
        return render(
            request,
            START_TEMPLATE,
            _build_start_context(
                session=session,
                new_card_values=values,
                new_card_errors=errors,
            ),
        )

    case = _session_case(session)
    from clients.models import StaffTask
    from clients.services.activity import log_client_activity
    from clients.services.tasks import create_auto_task

    # Persist the new-card answers, the confirmation file, and the derived staff
    # task as one unit. Without this, a failure while saving the uploaded file
    # could leave the MOS record marked "submitted" with no confirmation
    # document attached (or vice versa) — a half-saved state for client data.
    with transaction.atomic():
        _save_new_card_values(mos_data, values)
        if values.get("status") == NEW_CARD_STATUS_SUBMITTED_NO_NUMBER:
            create_auto_task(session.client, "case_number_missing", case=case, title=_("Запросить номер дела у клиента"))
        elif values.get("status") == NEW_CARD_STATUS_SUBMITTED_WITH_NUMBER and values.get("case_number"):
            tasks = StaffTask.objects.filter(
                client=session.client,
                case=case,
                task_type="case_number_missing",
                status__in=["open", "in_progress"],
            )
            if tasks.exists():
                tasks.update(
                    title=_("Проверить номер дела"),
                    description=_("Клиент указал номер дела новой подачи. Проверьте его и перенесите в основной номер дела.")
                )
            else:
                create_auto_task(
                    session.client,
                    "case_number_missing",
                    case=case,
                    title=_("Проверить номер дела"),
                    description=_("Клиент указал номер дела новой подачи. Проверьте его и перенесите в основной номер дела.")
                )

        if upload_form is not None:
            upload_client_document(
                client=session.client,
                doc_type=NEW_CARD_CONFIRMATION_DOC_TYPE,
                uploaded_document=upload_form.save(commit=False),
                actor=request.user if request.user.is_authenticated else None,
                parse_requested=False,
                case=case,
            )
        log_client_activity(
            client=session.client,
            actor=request.user if request.user.is_authenticated else None,
            event_type="new_card_application_updated",
            summary="Клиент обновил информацию о новой подаче на карту побыту",
            details="Клиент обновил информацию о новой подаче.",
            metadata={
                "status": values.get("status"),
                "has_case_number": bool(values.get("case_number")),
            }
        )

    mos_data.refresh_from_db()
    confirmation_document = _latest_new_card_confirmation_document(session.client, case)
    messages.success(request, _("Informacja o nowym wniosku została zapisana. / Информация о новом заявлении сохранена."))
    for warning in _new_card_missing_warnings(mos_data, confirmation_document):
        messages.warning(request, warning)
    return redirect("clients:onboarding_start", token=token)


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
    new_card_values: dict[str, str] | None = None,
    new_card_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    client = session.client
    case = _session_case(session)
    mos_data = MOSApplicationData.objects.filter(client=client, case=case).first()
    if mos_data is None:
        mos_data = MOSApplicationData(client=client, case=case)
    purpose_ctx = _purpose_context(client, mos_data)
    effective_purpose = str(purpose_ctx["effective_purpose"])
    language = translation.get_language() or client.language

    fingerprint_invitation_doc_type = DocumentType.WEZWANIE.value
    documents_qs = Document.objects.filter(client=client, archived_at__isnull=True)
    if case is not None:
        documents_qs = documents_qs.filter(case=case)
    existing_documents = list(documents_qs.order_by("document_type", "-uploaded_at"))
    existing_map = {document.document_type: document.id for document in existing_documents}
    new_card_confirmation_document = next(
        (document for document in existing_documents if document.document_type == NEW_CARD_CONFIRMATION_DOC_TYPE),
        None,
    )

    required_docs_catalog = DocumentRequirement.catalog_for(purpose=effective_purpose, language=language)

    import os

    from django.conf import settings
    support_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "support@example.com"))

    from datetime import date
    today = date.today()
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

        is_expired = False
        is_rejected = False
        is_verified = False
        is_awaiting_verification = False
        if doc_obj:
            is_expired = bool(doc_obj.expiry_date and doc_obj.expiry_date < today)
            is_rejected = bool(doc_obj.rejection_reason and not doc_obj.verified)
            is_verified = bool(doc_obj.verified)
            is_awaiting_verification = bool(not doc_obj.verified and not doc_obj.rejection_reason)

        checklist.append({
            "code": doc_type,
            "label": item["label"],
            "is_required": item["is_required"],
            "is_uploaded": is_uploaded,
            "doc_id": doc_obj.id if doc_obj else None,
            "verified": doc_obj.verified if doc_obj else False,
            "rejection_reason": doc_obj.rejection_reason if doc_obj else "",
            "is_expired": is_expired,
            "is_rejected": is_rejected,
            "is_verified": is_verified,
            "is_awaiting_verification": is_awaiting_verification,
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
        if document.document_type not in checklist_codes
        and document.document_type not in {fingerprint_invitation_doc_type, NEW_CARD_CONFIRMATION_DOC_TYPE}
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

    case_step = client.get_case_step()

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
        "new_card_confirmation_doc_type": NEW_CARD_CONFIRMATION_DOC_TYPE,
        "new_card_confirmation_document": new_card_confirmation_document,
        "new_card_values": new_card_values or _new_card_values_from_mos(mos_data),
        "new_card_errors": new_card_errors or {},
        "docs_total_count": docs_total_count,
        "docs_uploaded_count": docs_uploaded_count,
        "docs_required_pending_count": docs_required_pending_count,
        "passport_complete": passport_complete,
        "travel_complete": travel_complete,
        "support_email": support_email,
        "rejected_count": sum(1 for doc in checklist if doc.get("is_rejected")),
        "missing_case_number": bool(
            mos_data
            and mos_data.new_residence_card_application_status == "yes"
            and not mos_data.new_residence_card_case_number
        ),
        **purpose_ctx,
    }


def onboarding_start_contact(request: HttpRequest, token: str) -> HttpResponse:
    session = check_onboarding_session(token, request=request)
    if not session:
        return HttpResponseForbidden(_("Срок действия ссылки истёк или она недействительна."))

    auth_redirect = check_client_auth(request, session, token)
    if auth_redirect:
        return auth_redirect

    # Portal users must pick a case before any case-scoped step.
    case_redirect = _require_portal_case(request, session, token)
    if case_redirect:
        return case_redirect

    client = session.client
    case = _session_case(session)
    mos_data = MOSApplicationData.objects.filter(client=client, case=case).first()
    if mos_data is None:
        mos_data = MOSApplicationData(client=client, case=case)

    if request.method == "POST":
        mos_data, _created = _ensure_mos(client, case)
        if request.POST.get("action") == "new_card_application":
            return _handle_new_card_application_post(request, session=session, mos_data=mos_data, token=token)

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
