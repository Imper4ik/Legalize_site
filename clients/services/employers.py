from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from clients.models import Case, CaseEmployerAssignment, Company, EmployerChangeCandidate, StaffTask
from clients.models.company import normalize_company_name
from clients.services.activity import log_client_activity
from clients.services.tasks import close_auto_task, create_auto_task


def _digits(value: str | None, limit: int) -> str:
    return re.sub(r"\D", "", value or "")[:limit]


def company_matches(company: Company, *, name: str = "", nip: str = "", regon: str = "", krs: str = "") -> bool:
    proposed_ids = {"nip": _digits(nip, 10), "regon": _digits(regon, 14), "krs": _digits(krs, 10)}
    for field, proposed in proposed_ids.items():
        current = getattr(company, field, "") or ""
        if proposed and current:
            return proposed == current
    normalized = normalize_company_name(name)
    return bool(normalized and company.normalized_name and normalized == company.normalized_name)


def ensure_assignment(case: Case, *, actor: Any = None, source: str = "manual", document: Any = None) -> None:
    if case.archived_at is not None:
        return
    active = CaseEmployerAssignment.objects.filter(case=case, ended_at__isnull=True).first()
    if not case.company_id:
        if active:
            active.ended_at = timezone.now()
            active.save(update_fields=["ended_at"])
        return
    if active and active.company_id == case.company_id:
        return
    if active:
        active.ended_at = timezone.now()
        active.save(update_fields=["ended_at"])
    company = case.company
    if company is None:
        return
    CaseEmployerAssignment.objects.create(
        case=case, company=company, source=source, source_document=document, confirmed_by=actor
    )


def ensure_employer_capture_task(case: Case) -> StaffTask | None:
    """Keep a visible reminder when a work case reaches staff without an employer."""
    if (
        case.archived_at is not None
        or case.workflow_stage == "closed"
        or case.application_purpose != "work"
        or case.company_id
    ):
        return None
    return create_auto_task(
        case.client,
        "employer_review",
        case=case,
        title=_("Уточнить работодателя до отпечатков"),
        description=_("Работодатель не был указан при подаче. Его можно внести при проверке анкеты или на этапе отпечатков."),
    )


def propose_employer(
    *, case: Case | None, name: str = "", nip: str = "", regon: str = "", krs: str = "",
    document: Any = None, source: str = "document_ocr", confidence: str = "",
) -> EmployerChangeCandidate | None:
    if (
        case is None
        or case.archived_at is not None
        or case.workflow_stage == "closed"
        or case.application_purpose != "work"
    ):
        return None
    name = " ".join((name or "").split())[:255]
    nip, regon, krs = _digits(nip, 10), _digits(regon, 14), _digits(krs, 10)
    nip = nip if len(nip) == 10 else ""
    regon = regon if len(regon) in {9, 14} else ""
    krs = krs if len(krs) == 10 else ""
    if not any((name, nip, regon, krs)):
        return None
    current_company = case.company
    if current_company is not None and company_matches(current_company, name=name, nip=nip, regon=regon, krs=krs):
        ensure_assignment(case, source="existing")
        return None

    # The same employer may arrive through client onboarding, the fingerprints
    # check and one or more OCR documents. Keep one unresolved decision instead
    # of creating a new alert for every source (or every autosave revision).
    unresolved_statuses = {
        EmployerChangeCandidate.STATUS_PENDING,
        EmployerChangeCandidate.STATUS_NEEDS_INFO,
        EmployerChangeCandidate.STATUS_DEFERRED,
    }
    for existing in EmployerChangeCandidate.objects.filter(
        case=case,
        status__in=unresolved_statuses,
    ).order_by("-detected_at", "-id"):
        identifiers_match = any(
            proposed and current and proposed == current
            for proposed, current in (
                (nip, existing.proposed_nip),
                (regon, existing.proposed_regon),
                (krs, existing.proposed_krs),
            )
        )
        names_match = bool(
            name
            and existing.proposed_name
            and normalize_company_name(name) == normalize_company_name(existing.proposed_name)
        )
        if identifiers_match or names_match:
            return existing

    source_key = f"document:{document.pk}" if document is not None else source
    raw_fingerprint = f"{case.pk}|{normalize_company_name(name)}|{nip}|{regon}|{krs}|{source_key}"
    fingerprint = hashlib.sha256(raw_fingerprint.encode("utf-8")).hexdigest()
    with transaction.atomic():
        case = (
            Case.all_objects.select_related("client", "company")
            .select_for_update(of=("self",))
            .get(pk=case.pk)
        )
        if case.archived_at is not None or case.workflow_stage == "closed" or case.application_purpose != "work":
            return None
        current_company = case.company
        if current_company is not None and company_matches(
            current_company, name=name, nip=nip, regon=regon, krs=krs
        ):
            ensure_assignment(case, source="existing")
            return None
        candidate, created = EmployerChangeCandidate.objects.get_or_create(
            fingerprint=fingerprint,
            defaults={
                "case": case, "current_company": case.company, "source_document": document,
                "proposed_name": name, "proposed_nip": nip, "proposed_regon": regon,
                "proposed_krs": krs, "source": source, "confidence": confidence,
            },
        )
        if not created:
            return candidate
        is_change = bool(case.company_id)
        task = create_auto_task(
            case.client, "employer_review", case=case, document=document,
            title=(
                _("Проверить нового работодателя: %(employer)s")
                if is_change else _("Подтвердить работодателя: %(employer)s")
            ) % {"employer": candidate.proposed_label},
            description=(
                _("Система обнаружила работодателя, отличающегося от указанного в деле. Текущий работодатель не изменён.")
                if is_change else _("Работодатель указан впервые и требует проверки сотрудником.")
            ),
        )
        log_client_activity(
            client=case.client, case=case, document=document, task=task,
            event_type="client_updated", summary="Обнаружен возможный новый работодатель",
        )
        return candidate


def review_employer_candidate(
    *, candidate_id: int, decision: str, actor: Any, note: str = "", effective_from: date | None = None,
) -> EmployerChangeCandidate:
    allowed = {
        EmployerChangeCandidate.STATUS_CONFIRMED, EmployerChangeCandidate.STATUS_SAME,
        EmployerChangeCandidate.STATUS_OCR_ERROR, EmployerChangeCandidate.STATUS_NEEDS_INFO,
        EmployerChangeCandidate.STATUS_DEFERRED,
    }
    if decision not in allowed:
        raise ValidationError(_("Неизвестное решение по работодателю."))
    with transaction.atomic():
        candidate = EmployerChangeCandidate.objects.select_for_update().select_related("case", "case__client").get(pk=candidate_id)
        if candidate.status not in {
            EmployerChangeCandidate.STATUS_PENDING,
            EmployerChangeCandidate.STATUS_NEEDS_INFO,
            EmployerChangeCandidate.STATUS_DEFERRED,
        }:
            raise ValidationError(_("Эта проверка работодателя уже обработана."))
        case = Case.all_objects.select_for_update().get(pk=candidate.case_id)
        if case.archived_at is not None:
            raise ValidationError(_("Нельзя изменить работодателя в архивном деле."))
        if decision == EmployerChangeCandidate.STATUS_CONFIRMED and (
            case.workflow_stage == "closed" or case.application_purpose != "work"
        ):
            raise ValidationError(_("Нельзя подтвердить работодателя для закрытого или нерабочего дела."))
        if decision == EmployerChangeCandidate.STATUS_SAME and not case.company_id:
            raise ValidationError(_("Нельзя отметить работодателя как прежнего: в деле ещё нет подтверждённого работодателя."))

        if decision == EmployerChangeCandidate.STATUS_CONFIRMED:
            company = _resolve_or_create_company(candidate)
            current = CaseEmployerAssignment.objects.filter(case=case, ended_at__isnull=True).first()
            if current:
                current.ended_at = timezone.now()
                current.save(update_fields=["ended_at"])
            case.company = company
            case.save(update_fields=["company", "updated_at"])
            CaseEmployerAssignment.objects.create(
                case=case, company=company, source=candidate.source,
                source_document=candidate.source_document, confirmed_by=actor,
                effective_from=effective_from or candidate.effective_from,
            )

        candidate.status = decision
        if effective_from is not None:
            candidate.effective_from = effective_from
        candidate.review_note = (note or "").strip()
        candidate.reviewed_by = actor
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=["status", "effective_from", "review_note", "reviewed_by", "reviewed_at"])
        if decision not in {EmployerChangeCandidate.STATUS_NEEDS_INFO, EmployerChangeCandidate.STATUS_DEFERRED}:
            close_auto_task(case.client, "employer_review", case=case, document=candidate.source_document)
        log_client_activity(
            client=case.client, case=case, actor=actor, document=candidate.source_document,
            event_type="client_updated", summary="Проверка работодателя завершена",
        )
        return candidate


def _resolve_or_create_company(candidate: EmployerChangeCandidate) -> Company:
    query = Company.objects.none()
    if candidate.proposed_nip:
        query = Company.objects.filter(nip=candidate.proposed_nip)
    elif candidate.proposed_krs:
        query = Company.objects.filter(krs=candidate.proposed_krs)
    elif candidate.proposed_regon:
        query = Company.objects.filter(regon=candidate.proposed_regon)
    elif candidate.proposed_name:
        query = Company.objects.filter(normalized_name=normalize_company_name(candidate.proposed_name))
    company = query.order_by("id").first()
    if company:
        return company
    return Company.objects.create(
        name=candidate.proposed_name or f"NIP {candidate.proposed_nip}",
        nip=candidate.proposed_nip, regon=candidate.proposed_regon, krs=candidate.proposed_krs,
    )
