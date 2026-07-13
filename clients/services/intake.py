from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_date

from clients.models import (
    Case,
    CaseParticipant,
    Client,
    ClientIntakeSubmission,
    Company,
    MOSApplicationData,
)
from clients.services.activity import log_client_activity
from clients.services.onboarding_purposes import normalize_onboarding_purpose

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


@dataclass(frozen=True)
class IntakeConversionResult:
    intake: ClientIntakeSubmission
    client: Client
    case: Case
    mos_data: MOSApplicationData


def _dict_value(data: Any) -> dict[str, Any]:
    return dict(cast(dict[str, Any], data)) if isinstance(data, dict) else {}


def _parse_optional_date(value: Any) -> Any:
    if value in (None, ""):
        return None
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value
    parsed = parse_date(str(value))
    if parsed is None:
        raise ValidationError("Invalid date in intake submission.")
    return parsed


def _normalized_case_purpose(case_data: dict[str, Any]) -> tuple[str, str]:
    raw_purpose = case_data.get("application_purpose") or case_data.get("mos_purpose") or "study"
    try:
        selected_purpose = normalize_onboarding_purpose(str(raw_purpose))
    except ValueError as exc:
        raise ValidationError("Invalid application purpose in intake submission.") from exc
    application_purpose = "family" if selected_purpose in {"family_spouse", "family_child"} else selected_purpose
    family_role = selected_purpose if application_purpose == "family" else ""
    return application_purpose, family_role


def find_existing_client_conflicts(submission: ClientIntakeSubmission) -> QuerySet[Client]:
    personal_data = _dict_value(submission.personal_data)
    email = str(personal_data.get("email") or "").strip()
    phone = str(personal_data.get("phone") or "").strip()

    query = Q()
    if email:
        query |= Q(email__iexact=email)
    if phone:
        query |= Q(phone=phone)
    if not query:
        return Client.objects.none()
    return Client.objects.filter(query)


def convert_intake_submission(
    submission: ClientIntakeSubmission,
    *,
    actor: AbstractBaseUser | AnonymousUser | None = None,
    allow_conflicts: bool = False,
) -> IntakeConversionResult:
    """Create the CRM Client and primary Case from a submitted intake row.

    Personal identity/contact fields are copied to ``Client``. Process/workflow
    fields are copied to the primary ``Case``. Existing clients with matching
    email/phone are never merged implicitly; staff must pass ``allow_conflicts``
    after review.
    """

    if submission.status == ClientIntakeSubmission.STATUS_CONVERTED:
        if not submission.created_client_id or not submission.created_case_id:
            raise ValidationError("Converted intake is missing created client/case links.")
        client = Client.objects.get(pk=submission.created_client_id)
        case = Case.objects.get(pk=submission.created_case_id)
        mos_data, _ = MOSApplicationData.objects.get_or_create(client=client, case=case)
        return IntakeConversionResult(intake=submission, client=client, case=case, mos_data=mos_data)

    if submission.status not in {
        ClientIntakeSubmission.STATUS_SUBMITTED,
        ClientIntakeSubmission.STATUS_NEEDS_REVIEW,
    }:
        raise ValidationError("Only submitted intake rows can be converted.")

    if submission.expires_at is not None and submission.expires_at <= timezone.now():
        submission.status = ClientIntakeSubmission.STATUS_EXPIRED
        submission.save(update_fields=["status", "updated_at"])
        raise ValidationError("Intake submission has expired.")

    conflicts = find_existing_client_conflicts(submission)
    if conflicts.exists() and not allow_conflicts:
        submission.status = ClientIntakeSubmission.STATUS_NEEDS_REVIEW
        submission.save(update_fields=["status", "updated_at"])
        raise ValidationError("Intake matches an existing client and requires staff review.")

    personal_data = _dict_value(submission.personal_data)
    case_data = _dict_value(submission.case_data)
    first_name = str(personal_data.get("first_name") or "").strip()
    last_name = str(personal_data.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise ValidationError("Intake personal data must include first_name and last_name.")

    application_purpose, family_role = _normalized_case_purpose(case_data)
    language = str(personal_data.get("language") or case_data.get("language") or "pl").strip() or "pl"
    company = None
    company_id = case_data.get("company_id")
    if company_id:
        company = Company.objects.filter(pk=company_id).first()

    with transaction.atomic():
        client = Client.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=str(personal_data.get("email") or "").strip().lower(),
            phone=str(personal_data.get("phone") or "").strip(),
            birth_date=_parse_optional_date(personal_data.get("birth_date")),
            citizenship=str(personal_data.get("citizenship") or "").strip(),
            passport_num=(
                personal_data.get("passport_num")
                or personal_data.get("passport_number")
                or personal_data.get("document_number")
                or None
            ),
            language=language,
            application_purpose=application_purpose,
            basis_of_stay=str(case_data.get("basis_of_stay") or "").strip(),
            family_role=family_role,
            company=company,
            status=str(case_data.get("status") or "new").strip() or "new",
        )

        case, _created = Case.objects.get_or_create_primary_for_client(client)
        case.application_purpose = application_purpose
        case.application_type = str(case_data.get("application_type") or "").strip()
        case.basis_of_stay = str(case_data.get("basis_of_stay") or "").strip()
        case.status = str(case_data.get("status") or client.status or "new").strip() or "new"
        case.workflow_stage = str(case_data.get("workflow_stage") or "new_client").strip() or "new_client"
        case.submission_date = _parse_optional_date(case_data.get("submission_date"))
        case.fingerprints_date = _parse_optional_date(case_data.get("fingerprints_date"))
        case.decision_date = _parse_optional_date(case_data.get("decision_date"))
        case.decision_valid_until = _parse_optional_date(case_data.get("decision_valid_until"))
        case.company = company
        case.save(update_fields=[
            "application_purpose",
            "application_type",
            "basis_of_stay",
            "status",
            "workflow_stage",
            "submission_date",
            "fingerprints_date",
            "decision_date",
            "decision_valid_until",
            "company",
            "updated_at",
        ])

        CaseParticipant.objects.get_or_create(case=case, client=client, defaults={"role": "principal"})
        mos_data, _created_mos = MOSApplicationData.objects.get_or_create(client=client, case=case)
        mos_data.personal_data = {**_dict_value(mos_data.personal_data), **personal_data}
        passport_value = personal_data.get("passport_num") or personal_data.get("passport_number") or personal_data.get("document_number")
        if passport_value:
            passport_data = _dict_value(mos_data.passport_data)
            passport_data.setdefault("document_number", passport_value)
            mos_data.passport_data = passport_data
        selected_mos_purpose = str(case_data.get("mos_purpose") or case_data.get("application_purpose") or "").strip()
        if selected_mos_purpose:
            mos_data.mos_purpose = selected_mos_purpose
        if mos_data.status == "draft":
            mos_data.status = "client_completed"
        mos_data.save(update_fields=["personal_data", "passport_data", "mos_purpose", "status", "updated_at"])

        submission.created_client = client
        submission.created_case = case
        submission.converted_by = actor if getattr(actor, "is_authenticated", False) else None  # type: ignore[assignment]
        submission.converted_at = timezone.now()
        submission.status = ClientIntakeSubmission.STATUS_CONVERTED
        submission.save(update_fields=[
            "created_client",
            "created_case",
            "converted_by",
            "converted_at",
            "status",
            "updated_at",
        ])

        log_client_activity(
            client=client,
            case=case,
            actor=actor,
            event_type="client_created",
            summary="Client and case created from intake submission",
            metadata={"case_id": str(case.uuid), "status_tag": "submitted"},
        )

    return IntakeConversionResult(intake=submission, client=client, case=case, mos_data=mos_data)
