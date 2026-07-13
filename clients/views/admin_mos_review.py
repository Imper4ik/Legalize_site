import logging
from typing import Any, cast

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from clients.models import Client, MOSApplicationData
from clients.security.encrypted import safe_encrypted_attr
from clients.services.access import accessible_clients_queryset
from clients.services.activity import log_client_activity
from clients.services.case_context import purpose_for_case
from clients.services.mos_eligibility import evaluate_mos_eligibility
from clients.services.onboarding_purposes import (
    ALLOWED_ONBOARDING_PURPOSES,
    apply_onboarding_purpose_to_case,
    apply_onboarding_purpose_to_client,
    clear_onboarding_notifications_cache,
    purpose_label,
)
from clients.services.workflow_transitions import transition_case_workflow
from clients.views.base import role_required_view

logger = logging.getLogger(__name__)

APPLY_TO_CLIENT_FIELDS = (
    "first_name",
    "last_name",
    "email",
    "phone",
    "birth_date",
    "citizenship",
    "passport_num",
    "basis_of_stay",
    "legal_basis_end_date",
)


def _purpose_review_context(
    client: Client,
    mos_data: MOSApplicationData,
    case: Any = None,
) -> dict[str, object]:
    card_requirement_purpose = purpose_for_case(case) if case is not None else client.get_document_requirement_purpose()
    client_selected_purpose = mos_data.mos_purpose
    return {
        "client_card_purpose": getattr(case, "application_purpose", client.application_purpose),
        "client_card_purpose_label": purpose_label(card_requirement_purpose),
        "client_selected_purpose": client_selected_purpose,
        "client_selected_purpose_label": purpose_label(client_selected_purpose),
        "purpose_mismatch": bool(
            client_selected_purpose and client_selected_purpose != card_requirement_purpose
        ),
        "can_accept_client_purpose": client_selected_purpose in ALLOWED_ONBOARDING_PURPOSES,
    }


def _mos_client_update_values(mos_data: MOSApplicationData) -> dict[str, object]:
    # EncryptedJSONField stores dicts but django-stubs types it as text.
    personal_data = cast("dict[str, Any]", mos_data.personal_data) or {}
    passport_data = cast("dict[str, Any]", mos_data.passport_data) or {}
    stay_data = cast("dict[str, Any]", mos_data.stay_data) or {}

    values: dict[str, object] = {}
    for field_name in ("first_name", "last_name", "email", "phone", "citizenship"):
        value = str(personal_data.get(field_name) or "").strip()
        if value:
            values[field_name] = value

    birth_date = parse_date(str(personal_data.get("birth_date") or "").strip())
    if birth_date:
        values["birth_date"] = birth_date

    document_number = str(passport_data.get("document_number") or "").strip()
    if document_number:
        values["passport_num"] = document_number

    stay_basis = str(stay_data.get("stay_basis") or "").strip()
    if stay_basis:
        values["basis_of_stay"] = stay_basis

    if mos_data.legal_stay_until:
        values["legal_basis_end_date"] = mos_data.legal_stay_until

    return values


def _build_review_diffs(client: Client, mos_data: MOSApplicationData) -> list[dict[str, object]]:
    field_labels = {
        "first_name": _("Имя"),
        "last_name": _("Фамилия"),
        "email": _("Email"),
        "phone": _("Телефон"),
        "birth_date": _("Дата рождения"),
        "citizenship": _("Гражданство"),
        "passport_num": _("Номер паспорта"),
        "basis_of_stay": _("Основание пребывания"),
        "legal_basis_end_date": _("Легальное пребывание до"),
    }
    values = _mos_client_update_values(mos_data)
    diffs = []
    for field_name in APPLY_TO_CLIENT_FIELDS:
        if field_name not in values:
            continue
        old_value = safe_encrypted_attr(client, field_name) if field_name == "passport_num" else getattr(client, field_name)
        new_value = values[field_name]
        if old_value != new_value:
            diffs.append(
                {
                    "field": field_name,
                    "label": field_labels.get(field_name, field_name),
                    "old": old_value or "-",
                    "new": new_value or "-",
                }
            )
    return diffs



def _apply_mos_data_to_client(*, client: Client, mos_data: MOSApplicationData, actor: Any) -> list[str]:
    values = _mos_client_update_values(mos_data)
    changed_fields: list[str] = []
    for field_name in APPLY_TO_CLIENT_FIELDS:
        if field_name not in values:
            continue
        new_value = values[field_name]
        old_value = safe_encrypted_attr(client, field_name) if field_name == "passport_num" else getattr(client, field_name)
        if old_value != new_value:
            setattr(client, field_name, new_value)
            changed_fields.append(field_name)

    if changed_fields:
        client.save(update_fields=changed_fields)
        log_client_activity(
            client=client,
            actor=actor,
            event_type="mos_data_applied",
            summary="MOS questionnaire data applied to client card",
            metadata={"changed_fields": changed_fields},
        )
    return changed_fields


def _resolve_review_mos_data(
    request: HttpRequest, client: Client
) -> MOSApplicationData | None:
    """Resolve the case-scoped MOS record this review acts on.

    MOSApplicationData is one-per-case, so a client with several cases has
    several records; ``get(client=client)`` would raise MultipleObjectsReturned
    (HTTP 500). An explicit ``case`` uuid (GET or POST) selects the record;
    with exactly one record it is used directly; otherwise the caller shows a
    case picker instead of guessing.
    """
    mos_records = MOSApplicationData.objects.filter(client=client).select_related("case")
    case_uuid = (request.POST.get("case") or request.GET.get("case") or "").strip()
    if case_uuid:
        return get_object_or_404(mos_records, case__uuid=case_uuid)

    records = list(mos_records[:2])
    if not records:
        from django.http import Http404

        raise Http404("No MOS application data for this client.")
    if len(records) == 1:
        return records[0]
    return None


def _review_redirect(client: Client, mos_data: MOSApplicationData) -> HttpResponse:
    from django.urls import reverse

    url = reverse("clients:admin_mos_review", kwargs={"client_id": client.id})
    if mos_data.case is not None:
        url = f"{url}?case={mos_data.case.uuid}"
    return redirect(url)


@role_required_view("Admin", "Manager", "Staff")
def admin_mos_review(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.defer("passport_num")), id=client_id)
    mos_data = _resolve_review_mos_data(request, client)
    if mos_data is None:
        # Several case-scoped questionnaires: let the staffer pick the case
        # explicitly instead of failing or silently choosing one.
        mos_records = (
            MOSApplicationData.objects.filter(client=client)
            .select_related("case")
            .order_by("-updated_at")
        )
        return render(
            request,
            "clients/mos_review_select_case.html",
            {"client": client, "mos_records": mos_records},
        )
    # Process transitions act on the MOS record's case (spec §4); the client is
    # never used as the process carrier.
    case = mos_data.case
    if case is None:
        from clients.services.cases import resolve_single_active_case

        case = resolve_single_active_case(client)
    if case is None:
        messages.error(request, _("Не удалось определить дело для этой анкеты. Выберите дело в карточке клиента."))
        return redirect("clients:client_detail", pk=client.id)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            changed_fields = _apply_mos_data_to_client(client=client, mos_data=mos_data, actor=request.user)
            mos_data.status = "mos_package_ready"
            mos_data.staff_reviewed_at = timezone.now()
            mos_data.staff_reviewed_by = cast(Any, request.user)
            mos_data.save(update_fields=["status", "staff_reviewed_at", "staff_reviewed_by"])
            if changed_fields:
                messages.success(request, _("Questionnaire approved and client card updated."))
            else:
                messages.success(request, _("Questionnaire approved. No client card fields changed."))
            return redirect("clients:client_detail", pk=client.id)
        elif action == "accept_client_purpose":
            selected_purpose = mos_data.mos_purpose
            if selected_purpose not in ALLOWED_ONBOARDING_PURPOSES:
                messages.error(request, _("Cannot apply this purpose to the client card."))
                return _review_redirect(client, mos_data)
            if case is not None:
                changed_fields = apply_onboarding_purpose_to_case(case, selected_purpose)
                event_type = "mos_case_purpose_applied"
                summary = "Client-selected MOS purpose applied to Case"
            else:
                changed_fields = apply_onboarding_purpose_to_client(client, selected_purpose)
                event_type = "mos_purpose_applied"
                summary = "Client-selected MOS purpose applied to client card"
            clear_onboarding_notifications_cache(client)
            log_client_activity(
                client=client,
                case=case,
                actor=request.user,
                event_type=event_type,
                summary=summary,
                metadata={"changed_fields": changed_fields},
            )
            messages.success(request, _("Client-selected purpose applied."))
            return _review_redirect(client, mos_data)
        elif action == "request_correction":
            mos_data.status = "needs_correction"
            mos_data.correction_message = request.POST.get("correction_message", "")
            mos_data.save(update_fields=["status", "correction_message"])
            messages.warning(request, _("Correction requested from client."))
            return redirect("clients:client_detail", pk=client.id)
        elif action == "mark_submitted":
            try:
                with transaction.atomic():
                    transition_case_workflow(case=case, target_stage="application_submitted", actor=request.user)
                    mos_data.status = "submitted_in_mos"
                    mos_data.save(update_fields=["status"])
            except ValidationError as exc:
                messages.error(request, str(exc))
                return _review_redirect(client, mos_data)
            except Exception:
                logger.exception("Unexpected error while marking MOS application submitted", extra={"client_id": client.id})
                messages.error(request, _("Unexpected error while updating application status."))
                return _review_redirect(client, mos_data)
            messages.success(request, _("Status: submitted in MOS."))
            return _review_redirect(client, mos_data)
        elif action == "mark_fingerprints":
            try:
                with transaction.atomic():
                    next_stage = "waiting_decision" if case.fingerprints_date and case.fingerprints_date <= timezone.localdate() else "fingerprints"
                    transition_case_workflow(case=case, target_stage=next_stage, actor=request.user)
                    mos_data.status = "fingerprints"
                    mos_data.save(update_fields=["status"])
            except ValidationError as exc:
                messages.error(request, str(exc))
                return _review_redirect(client, mos_data)
            except Exception:
                logger.exception("Unexpected error while marking MOS fingerprints", extra={"client_id": client.id})
                messages.error(request, _("Unexpected error while updating application status."))
                return _review_redirect(client, mos_data)
            messages.success(request, _("Status: fingerprints completed."))
            return _review_redirect(client, mos_data)
        elif action == "mark_waiting":
            if not case.fingerprints_date:
                messages.error(request, _("Cannot mark waiting decision without fingerprints date."))
                return _review_redirect(client, mos_data)
            try:
                with transaction.atomic():
                    transition_case_workflow(case=case, target_stage="waiting_decision", actor=request.user)
                    mos_data.status = "waiting_decision"
                    mos_data.save(update_fields=["status"])
            except ValidationError as exc:
                messages.error(request, str(exc))
                return _review_redirect(client, mos_data)
            messages.success(request, _("Status: waiting for decision."))
            return _review_redirect(client, mos_data)
        elif action == "mark_decision":
            if not case.decision_date:
                messages.error(request, _("Cannot mark decision received without decision date."))
                return _review_redirect(client, mos_data)
            try:
                with transaction.atomic():
                    transition_case_workflow(case=case, target_stage="decision_received", actor=request.user)
                    mos_data.status = "decision_received"
                    mos_data.save(update_fields=["status"])
            except ValidationError as exc:
                messages.error(request, str(exc))
                return _review_redirect(client, mos_data)
            messages.success(request, _("Status: decision received."))
            return _review_redirect(client, mos_data)

    passport_doc = client.documents.filter(document_type="passport").order_by("-uploaded_at").first()
    mos_eligibility = evaluate_mos_eligibility(client, mos_data)

    return render(
        request,
        "clients/mos_review.html",
        {
            "client": client,
            "mos_data": mos_data,
            "case": case,
            "review_diffs": _build_review_diffs(client, mos_data),
            "passport_doc": passport_doc,
            "mos_eligibility": mos_eligibility,
            **_purpose_review_context(client, mos_data, case),
        },
    )

