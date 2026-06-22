from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.db import migrations, transaction


UNAVAILABLE_MARKER = "[encrypted value unavailable]"


def _normalize_case_number(value: object) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def _hash_case_number(value: object) -> str:
    normalized = _normalize_case_number(value)
    if not normalized:
        return ""
    secret = str(getattr(settings, "SECRET_KEY", ""))
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def _clean_sensitive_text(value: object) -> str:
    text = str(value or "")
    if text == UNAVAILABLE_MARKER:
        return ""
    return text


def _first_case_id_for_client(Case, client_id: int) -> int | None:
    return (
        Case._base_manager.filter(client_id=client_id)
        .order_by("opened_at", "id")
        .values_list("id", flat=True)
        .first()
    )


def _build_case_payload(client) -> dict[str, object]:
    case_number = _clean_sensitive_text(getattr(client, "case_number", ""))
    payload = {
        "client_id": client.pk,
        "internal_number": case_number,
        "authority_case_number": case_number,
        "authority_case_number_hash": _hash_case_number(case_number),
        "status": getattr(client, "status", "new") or "new",
        "workflow_stage": getattr(client, "workflow_stage", "new_client") or "new_client",
        "application_purpose": getattr(client, "application_purpose", "") or "",
        "basis_of_stay": getattr(client, "basis_of_stay", "") or "",
        "submission_date": getattr(client, "submission_date", None),
        "fingerprints_date": getattr(client, "fingerprints_date", None),
        "fingerprints_time": getattr(client, "fingerprints_time", None),
        "fingerprints_location": getattr(client, "fingerprints_location", "") or "",
        "fingerprints_ticket": getattr(client, "fingerprints_ticket", "") or "",
        "fingerprints_list": getattr(client, "fingerprints_list", "") or "",
        "fingerprints_info": getattr(client, "fingerprints_info", "") or "",
        "decision_date": getattr(client, "decision_date", None),
        "assigned_staff_id": getattr(client, "assigned_staff_id", None),
        "company_id": getattr(client, "company_id", None),
        "archived_at": getattr(client, "archived_at", None),
        "is_test_data": getattr(client, "is_test_data", False),
        "is_demo_data": getattr(client, "is_demo_data", False),
    }
    created_at = getattr(client, "created_at", None)
    if created_at is not None:
        payload["opened_at"] = created_at.date()
    return payload


def _create_primary_cases(apps) -> dict[int, int]:
    Client = apps.get_model("clients", "Client")
    Case = apps.get_model("clients", "Case")
    case_by_client: dict[int, int] = {}
    for client in Client._base_manager.order_by("pk").iterator(chunk_size=1000):
        case_id = _first_case_id_for_client(Case, client.pk)
        if case_id is None:
            case = Case._base_manager.create(**_build_case_payload(client))
            case_id = case.pk
        case_by_client[client.pk] = case_id
    return case_by_client


def _primary_case_id(case_by_client: dict[int, int], client_id: int | None) -> int | None:
    if client_id is None:
        return None
    return case_by_client.get(client_id)


def _bulk_link_by_client(Model, case_by_client: dict[int, int]) -> None:
    for client_id, case_id in case_by_client.items():
        Model._base_manager.filter(client_id=client_id, case_id__isnull=True).update(case_id=case_id)


def _link_source_models(apps, case_by_client: dict[int, int]) -> None:
    Document = apps.get_model("clients", "Document")
    DocumentVersion = apps.get_model("clients", "DocumentVersion")
    Payment = apps.get_model("clients", "Payment")
    Reminder = apps.get_model("clients", "Reminder")
    StaffTask = apps.get_model("clients", "StaffTask")
    ClientActivity = apps.get_model("clients", "ClientActivity")
    ClientOnboardingSession = apps.get_model("clients", "ClientOnboardingSession")
    DocumentProcessingJob = apps.get_model("clients", "DocumentProcessingJob")

    for version in DocumentVersion._base_manager.filter(case_id__isnull=True).select_related("document").iterator(chunk_size=1000):
        case_id = getattr(version.document, "case_id", None) if version.document_id else None
        if case_id:
            DocumentVersion._base_manager.filter(pk=version.pk, case_id__isnull=True).update(case_id=case_id)

    for job in DocumentProcessingJob._base_manager.filter(case_id__isnull=True).select_related("document").iterator(chunk_size=1000):
        case_id = getattr(job.document, "case_id", None) if job.document_id else None
        if case_id:
            DocumentProcessingJob._base_manager.filter(pk=job.pk, case_id__isnull=True).update(case_id=case_id)

    for session in ClientOnboardingSession._base_manager.filter(case_id__isnull=True).select_related("payment").iterator(chunk_size=1000):
        case_id = getattr(session.payment, "case_id", None) if session.payment_id else None
        case_id = case_id or _primary_case_id(case_by_client, session.client_id)
        if case_id:
            ClientOnboardingSession._base_manager.filter(pk=session.pk, case_id__isnull=True).update(case_id=case_id)

    for reminder in Reminder._base_manager.filter(case_id__isnull=True).select_related("payment", "document", "custom_document_requirement").iterator(chunk_size=1000):
        case_id = None
        if reminder.payment_id:
            case_id = getattr(reminder.payment, "case_id", None)
        if case_id is None and reminder.document_id:
            case_id = getattr(reminder.document, "case_id", None)
        if case_id is None and reminder.custom_document_requirement_id:
            case_id = getattr(reminder.custom_document_requirement, "case_id", None)
        case_id = case_id or _primary_case_id(case_by_client, reminder.client_id)
        if case_id:
            Reminder._base_manager.filter(pk=reminder.pk, case_id__isnull=True).update(case_id=case_id)

    for task in StaffTask._base_manager.filter(case_id__isnull=True).select_related("document", "payment").iterator(chunk_size=1000):
        case_id = None
        if task.document_id:
            case_id = getattr(task.document, "case_id", None)
        if case_id is None and task.payment_id:
            case_id = getattr(task.payment, "case_id", None)
        case_id = case_id or _primary_case_id(case_by_client, task.client_id)
        if case_id:
            StaffTask._base_manager.filter(pk=task.pk, case_id__isnull=True).update(case_id=case_id)

    for activity in ClientActivity._base_manager.filter(case_id__isnull=True).select_related("document", "payment", "task").iterator(chunk_size=1000):
        case_id = None
        if activity.document_id:
            case_id = getattr(activity.document, "case_id", None)
        if case_id is None and activity.payment_id:
            case_id = getattr(activity.payment, "case_id", None)
        if case_id is None and activity.task_id:
            case_id = getattr(activity.task, "case_id", None)
        case_id = case_id or _primary_case_id(case_by_client, activity.client_id)
        if case_id:
            ClientActivity._base_manager.filter(pk=activity.pk, case_id__isnull=True).update(case_id=case_id)


def _backfill_new_card_application_data(apps) -> None:
    Case = apps.get_model("clients", "Case")
    MOSApplicationData = apps.get_model("clients", "MOSApplicationData")
    for mos in MOSApplicationData._base_manager.filter(case_id__isnull=False).iterator(chunk_size=1000):
        data = {
            "new_residence_card_application_status": getattr(mos, "new_residence_card_application_status", ""),
            "new_residence_card_case_number": _clean_sensitive_text(getattr(mos, "new_residence_card_case_number", "")),
            "new_residence_card_submitted_at": getattr(mos, "new_residence_card_submitted_at", None).isoformat() if getattr(mos, "new_residence_card_submitted_at", None) else "",
            "new_residence_card_comment": getattr(mos, "new_residence_card_comment", "") or "",
        }
        Case._base_manager.filter(pk=mos.case_id).update(new_card_application_data=data)


def _encrypt_json_fields(apps) -> None:
    json_targets = [
        ("Document", ["parsed_data"]),
        ("MOSApplicationData", [
            "personal_data",
            "passport_data",
            "address_data",
            "stay_data",
            "previous_stays",
            "travel_history",
            "insurance_data",
            "financial_data",
            "legal_declarations",
        ]),
        ("PeselApplication", ["pesel_form_data"]),
        ("Case", ["new_card_application_data"]),
    ]
    for model_name, field_names in json_targets:
        Model = apps.get_model("clients", model_name)
        for row in Model._base_manager.order_by("pk").iterator(chunk_size=500):
            changed_fields: list[str] = []
            for field_name in field_names:
                value = getattr(row, field_name, None)
                if value is None or value == "" or str(value) == UNAVAILABLE_MARKER:
                    continue
                changed_fields.append(field_name)
            if changed_fields:
                row.save(update_fields=changed_fields)


def backfill_cases_and_encrypt_json(apps, schema_editor) -> None:
    with transaction.atomic():
        case_by_client = _create_primary_cases(apps)

        for model_name in [
            "Document",
            "Payment",
            "ClientDocumentRequirement",
            "ClientFamilyMemberMOS",
            "MOSApplicationData",
            "PeselApplication",
            "EmailLog",
            "WniosekSubmission",
        ]:
            _bulk_link_by_client(apps.get_model("clients", model_name), case_by_client)

        _link_source_models(apps, case_by_client)
        _backfill_new_card_application_data(apps)
        _encrypt_json_fields(apps)


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0095_documentversion_docver_case_version_idx"),
    ]

    operations = [
        migrations.RunPython(backfill_cases_and_encrypt_json, migrations.RunPython.noop),
    ]
