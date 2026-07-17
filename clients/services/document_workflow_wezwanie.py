"""Wezwanie payload and client/case update builders, extracted from
``document_workflow``.

Pure(-ish) functions that translate parsed or confirmed wezwanie data into
storage payloads and case-first field updates. No dependency on the job
orchestration or OCR pipeline, so they live here and are imported back into
``document_workflow`` to keep callers and mock targets unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.utils.dateparse import parse_date, parse_time
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.models import Client
from clients.security.encrypted import require_encrypted_text
from clients.services.permissions import user_can_run_ocr_review
from clients.services.wezwanie_parser import WezwanieData


def _has_meaningful_parsed_data(parsed: WezwanieData) -> bool:
    return bool(parsed.text.strip()) or any(
        [
            parsed.case_number,
            parsed.fingerprints_date,
            parsed.fingerprints_time,
            parsed.fingerprints_location,
            parsed.ticket_number,
            parsed.list_name,
            parsed.application_status_code,
            parsed.decision_date,
            parsed.full_name,
        ]
    )


def _has_name_mismatch(parsed_full_name: str | None, client: Client) -> bool:
    if not parsed_full_name or not client.first_name or not client.last_name:
        return False
    normalized_name = parsed_full_name.lower()
    return (
        client.first_name.lower() not in normalized_name
        or client.last_name.lower() not in normalized_name
    )


def _build_wezwanie_payload(parsed: WezwanieData) -> dict[str, Any]:
    first_name = ""
    last_name = ""
    if parsed.full_name:
        name_parts = parsed.full_name.split()
        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])

    return {
        "full_name": parsed.full_name or "",
        "first_name": first_name,
        "last_name": last_name,
        "case_number": parsed.case_number or "",
        "fingerprints_date": parsed.fingerprints_date.isoformat() if parsed.fingerprints_date else "",
        "fingerprints_date_display": parsed.fingerprints_date.strftime("%d.%m.%Y")
        if parsed.fingerprints_date
        else "",
        "fingerprints_time": parsed.fingerprints_time or "",
        "fingerprints_location": parsed.fingerprints_location or "",
        "ticket_number": parsed.ticket_number or "",
        "list_name": parsed.list_name or "",
        "application_status_code": parsed.application_status_code or "",
        "decision_date": parsed.decision_date.isoformat() if parsed.decision_date else "",
        "decision_date_display": parsed.decision_date.strftime("%d.%m.%Y")
        if parsed.decision_date
        else "",
        "required_documents": list(parsed.required_documents or []),
    }


def _append_required_documents_update(parsed: WezwanieData, auto_updates: list[str]) -> None:
    _append_required_documents_update_from_codes(parsed.required_documents, auto_updates)


def _append_required_documents_update_from_codes(doc_codes: list[str] | None, auto_updates: list[str]) -> None:
    if not doc_codes:
        return

    doc_labels: list[str] = []
    for doc_code in doc_codes:
        try:
            doc_labels.append(str(DocumentType(doc_code).label))
        except ValueError:
            doc_labels.append(doc_code)

    if doc_labels:
        auto_updates.append(
            _("required documents detected: %(val)s") % {"val": ", ".join(doc_labels)}
        )


DECISION_DATE_WRITABLE_STAGES = {"waiting_decision", "decision_received", "closed"}


def _can_apply_decision_date(case: Any, actor: Any) -> bool:
    if case is None or not user_can_run_ocr_review(actor):
        return False
    if case.workflow_stage not in DECISION_DATE_WRITABLE_STAGES:
        return False
    if case.workflow_stage == "waiting_decision" and not case.fingerprints_date:
        return False
    return True


def _apply_parsed_client_updates(
    case: Any,
    client: Client,
    parsed: WezwanieData,
    *,
    actor: Any = None,
) -> tuple[list[str], list[str], list[str]]:
    """Apply parsed wezwanie data case-first.

    Process data (authority case number, fingerprints, decision date, purpose)
    is written to the case; only genuinely permanent data — a missing client
    name — is written to the client. This keeps two cases of the same client
    from contaminating each other (spec section 5).

    Returns ``(case_fields, client_fields, auto_updates)``.
    """
    case_fields: list[str] = []
    client_fields: list[str] = []
    auto_updates: list[str] = []

    if case is not None:
        current_case_number = (
            require_encrypted_text(case, "authority_case_number")
            if parsed.case_number
            else None
        )
        if parsed.case_number and parsed.case_number != current_case_number:
            case.authority_case_number = parsed.case_number
            case_fields.append("authority_case_number")
            auto_updates.append(_("case number updated"))

        if parsed.fingerprints_date and parsed.fingerprints_date != case.fingerprints_date:
            case.fingerprints_date = parsed.fingerprints_date
            case_fields.append("fingerprints_date")
            auto_updates.append(
                _("fingerprints date: %(val)s")
                % {"val": parsed.fingerprints_date.strftime("%d.%m.%Y")}
            )

        parsed_fingerprints_time = parse_time(parsed.fingerprints_time or "")
        if parsed_fingerprints_time and parsed_fingerprints_time != case.fingerprints_time:
            case.fingerprints_time = parsed_fingerprints_time
            case_fields.append("fingerprints_time")

        if parsed.fingerprints_location and parsed.fingerprints_location != (case.fingerprints_location or ""):
            case.fingerprints_location = parsed.fingerprints_location
            case_fields.append("fingerprints_location")

        if parsed.decision_date and parsed.decision_date != case.decision_date:
            if _can_apply_decision_date(case, actor):
                case.decision_date = parsed.decision_date
                case_fields.append("decision_date")
                auto_updates.append(
                    _("decision date: %(val)s") % {"val": parsed.decision_date.strftime("%d.%m.%Y")}
                )
            else:
                auto_updates.append(_("decision date skipped: case must already be waiting for decision"))

        if parsed.ticket_number and parsed.ticket_number != case.fingerprints_ticket:
            case.fingerprints_ticket = parsed.ticket_number
            case_fields.append("fingerprints_ticket")
            auto_updates.append(_("ticket number: %(val)s") % {"val": parsed.ticket_number})

        if parsed.list_name and parsed.list_name != case.fingerprints_list:
            case.fingerprints_list = parsed.list_name
            case_fields.append("fingerprints_list")
            auto_updates.append(_("list: %(val)s") % {"val": parsed.list_name})

        # Map P/S/K to application purpose if not set
        if parsed.application_status_code:
            purpose_map = {"P": "work", "S": "study", "K": "family"}
            mapped_purpose = purpose_map.get(parsed.application_status_code)
            if mapped_purpose and case.application_purpose != mapped_purpose:
                case.application_purpose = mapped_purpose
                case_fields.append("application_purpose")
                auto_updates.append(_("application purpose set to: %(val)s") % {"val": mapped_purpose})

    # Permanent client data only: fill a missing name.
    if parsed.full_name and (not client.first_name or not client.last_name):
        name_parts = parsed.full_name.split()
        if len(name_parts) >= 2:
            client.first_name = name_parts[0]
            client.last_name = " ".join(name_parts[1:])
            client_fields.extend(["first_name", "last_name"])
            auto_updates.append(_("client name updated"))

    return case_fields, client_fields, auto_updates


def _build_confirmed_wezwanie_payload(confirmation_data: Mapping[str, str]) -> dict[str, Any]:
    safe_field_names = (
        "first_name",
        "last_name",
        "case_number",
        "fingerprints_date",
        "fingerprints_time",
        "fingerprints_location",
        "ticket_number",
        "list_name",
        "application_status_code",
        "decision_date",
    )
    confirmed_fields = [
        field_name
        for field_name in safe_field_names
        if (confirmation_data.get(field_name) or "").strip()
    ]
    return {
        "confirmed": True,
        "confirmed_fields": confirmed_fields,
        "raw_text_removed": True,
    }


def _build_confirmed_wezwanie_notification_data(confirmation_data: Mapping[str, str]) -> WezwanieData:
    fingerprints_date_raw = (confirmation_data.get("fingerprints_date") or "").strip()
    fingerprints_date = parse_date(fingerprints_date_raw) if fingerprints_date_raw else None
    return WezwanieData(
        text="",
        fingerprints_date=fingerprints_date,
        wezwanie_type="fingerprints" if fingerprints_date else None,
    )


def _apply_confirmation_updates(
    case: Any,
    client: Client,
    confirmation_data: Mapping[str, str],
    *,
    actor: Any = None,
) -> tuple[list[str], list[str], list[str]]:
    """Apply confirmed wezwanie data case-first.

    Returns ``(case_fields, client_fields, auto_updates)``. Process data goes to
    the case; only the permanent client name goes to the client.
    """
    case_fields: list[str] = []
    client_fields: list[str] = []
    auto_updates: list[str] = []

    first_name = (confirmation_data.get("first_name") or "").strip()
    last_name = (confirmation_data.get("last_name") or "").strip()
    case_number = (confirmation_data.get("case_number") or "").strip()
    fingerprints_date_raw = (confirmation_data.get("fingerprints_date") or "").strip()
    fingerprints_time_raw = (confirmation_data.get("fingerprints_time") or "").strip()
    fingerprints_location = (confirmation_data.get("fingerprints_location") or "").strip()
    decision_date_raw = (confirmation_data.get("decision_date") or "").strip()

    if first_name and first_name != client.first_name:
        client.first_name = first_name
        client_fields.append("first_name")

    if last_name and last_name != client.last_name:
        client.last_name = last_name
        client_fields.append("last_name")

    if case is not None:
        current_case_number = (
            require_encrypted_text(case, "authority_case_number")
            if case_number
            else None
        )
        if case_number and case_number != current_case_number:
            case.authority_case_number = case_number
            case_fields.append("authority_case_number")
            auto_updates.append(_("case number updated"))

        fingerprints_date = parse_date(fingerprints_date_raw) if fingerprints_date_raw else None
        if fingerprints_date and fingerprints_date != case.fingerprints_date:
            case.fingerprints_date = fingerprints_date
            case_fields.append("fingerprints_date")
            auto_updates.append(
                _("fingerprints date: %(val)s") % {"val": fingerprints_date.strftime("%d.%m.%Y")}
            )

        fingerprints_time = parse_time(fingerprints_time_raw) if fingerprints_time_raw else None
        if fingerprints_time and fingerprints_time != case.fingerprints_time:
            case.fingerprints_time = fingerprints_time
            case_fields.append("fingerprints_time")

        if fingerprints_location and fingerprints_location != (case.fingerprints_location or ""):
            case.fingerprints_location = fingerprints_location
            case_fields.append("fingerprints_location")

        ticket_number = (confirmation_data.get("ticket_number") or "").strip()
        if ticket_number and ticket_number != case.fingerprints_ticket:
            case.fingerprints_ticket = ticket_number
            case_fields.append("fingerprints_ticket")

        list_name = (confirmation_data.get("list_name") or "").strip()
        if list_name and list_name != case.fingerprints_list:
            case.fingerprints_list = list_name
            case_fields.append("fingerprints_list")

        status_code = (confirmation_data.get("application_status_code") or "").strip()
        if status_code:
            purpose_map = {"P": "work", "S": "study", "K": "family"}
            mapped_purpose = purpose_map.get(status_code)
            if mapped_purpose and case.application_purpose != mapped_purpose:
                case.application_purpose = mapped_purpose
                case_fields.append("application_purpose")

        decision_date = parse_date(decision_date_raw) if decision_date_raw else None
        if decision_date and decision_date != case.decision_date:
            if _can_apply_decision_date(case, actor):
                case.decision_date = decision_date
                case_fields.append("decision_date")
                auto_updates.append(
                    _("decision date: %(val)s") % {"val": decision_date.strftime("%d.%m.%Y")}
                )
            else:
                auto_updates.append(_("decision date skipped: case must already be waiting for decision"))

    return case_fields, client_fields, auto_updates
