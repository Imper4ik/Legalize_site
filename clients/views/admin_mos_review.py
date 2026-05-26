from typing import Any, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from clients.models import Client, MOSApplicationData
from clients.services.access import accessible_clients_queryset
from clients.services.workflow_transitions import transition_client_workflow
from django.core.exceptions import ValidationError
from clients.services.activity import log_client_activity
from clients.views.base import role_required_view


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


def _mos_client_update_values(mos_data: MOSApplicationData) -> dict[str, object]:
    personal_data = mos_data.personal_data or {}
    passport_data = mos_data.passport_data or {}
    stay_data = mos_data.stay_data or {}

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
    values = _mos_client_update_values(mos_data)
    diffs = []
    for field_name in APPLY_TO_CLIENT_FIELDS:
        if field_name not in values:
            continue
        old_value = getattr(client, field_name)
        new_value = values[field_name]
        if old_value != new_value:
            diffs.append(
                {
                    "field": field_name,
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
        if getattr(client, field_name) != new_value:
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


@role_required_view("Admin", "Manager", "Staff")
def admin_mos_review(request: HttpRequest, client_id: int) -> HttpResponse:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), id=client_id)
    mos_data = get_object_or_404(MOSApplicationData, client=client)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "approve":
            changed_fields = _apply_mos_data_to_client(client=client, mos_data=mos_data, actor=request.user)
            mos_data.status = "mos_package_ready"
            mos_data.staff_reviewed_at = timezone.now()
            mos_data.staff_reviewed_by = cast(Any, request.user)
            mos_data.save(update_fields=["status", "staff_reviewed_at", "staff_reviewed_by"])
            if changed_fields:
                messages.success(request, "Questionnaire approved and client card updated.")
            else:
                messages.success(request, "Questionnaire approved. No client card fields changed.")
            return redirect("clients:client_detail", pk=client.id)
        elif action == "request_correction":
            mos_data.status = "needs_correction"
            mos_data.correction_message = request.POST.get("correction_message", "")
            mos_data.save(update_fields=["status", "correction_message"])
            messages.warning(request, "Correction requested from client.")
            return redirect("clients:client_detail", pk=client.id)
        elif action == "mark_submitted":
            mos_data.status = "submitted_in_mos"
            mos_data.save(update_fields=["status"])
            try:
                transition_client_workflow(client=client, target_stage="application_submitted", actor=request.user)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("clients:admin_mos_review", client_id=client.id)
            messages.success(request, "Status: submitted in MOS.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_fingerprints":
            mos_data.status = "fingerprints"
            mos_data.save(update_fields=["status"])
            try:
                next_stage = "waiting_decision" if client.fingerprints_date and client.fingerprints_date <= timezone.localdate() else "fingerprints"
                transition_client_workflow(client=client, target_stage=next_stage, actor=request.user)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("clients:admin_mos_review", client_id=client.id)
            messages.success(request, "Status: fingerprints completed.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_waiting":
            if not client.fingerprints_date:
                messages.error(request, "Cannot mark waiting decision without fingerprints date.")
                return redirect("clients:admin_mos_review", client_id=client.id)
            mos_data.status = "waiting_decision"
            mos_data.save(update_fields=["status"])
            try:
                transition_client_workflow(client=client, target_stage="waiting_decision", actor=request.user)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("clients:admin_mos_review", client_id=client.id)
            messages.success(request, "Status: waiting for decision.")
            return redirect("clients:admin_mos_review", client_id=client.id)
        elif action == "mark_decision":
            if not client.decision_date:
                messages.error(request, "Cannot mark decision received without decision date.")
                return redirect("clients:admin_mos_review", client_id=client.id)
            mos_data.status = "decision_received"
            mos_data.save(update_fields=["status"])
            try:
                transition_client_workflow(client=client, target_stage="decision_received", actor=request.user)
            except ValidationError as exc:
                messages.error(request, str(exc))
                return redirect("clients:admin_mos_review", client_id=client.id)
            messages.success(request, "Status: decision received.")
            return redirect("clients:admin_mos_review", client_id=client.id)

    return render(
        request,
        "clients/mos_review.html",
        {
            "client": client,
            "mos_data": mos_data,
            "review_diffs": _build_review_diffs(client, mos_data),
        },
    )
