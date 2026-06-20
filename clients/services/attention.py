from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.db.models import Q, QuerySet
from django.utils import timezone

from clients.constants import DocumentType

ATTENTION_FILTERS = (
    "legal_stay",
    "expired_documents",
    "expiring_documents",
    "unverified_documents",
    "overdue_payments",
    "failed_emails",
    "fingerprints_email",
    "overdue_tasks",
    "wezwanie_missing_case",
    "new_card_missing_case",
)


def _legal_stay_attention_q(today: date) -> Q:
    cutoff = today + timedelta(days=30)
    return Q(workflow_stage__in=["new_client", "document_collection"]) & (
        Q(legal_basis_end_date__isnull=False, legal_basis_end_date__lte=cutoff)
        | Q(
            legal_basis_end_date__isnull=True,
            mos_application_data__legal_stay_until__isnull=False,
            mos_application_data__legal_stay_until__lte=cutoff,
        )
    )


def _missing_case_number_q() -> Q:
    return Q(case_number_hash__isnull=True) | Q(case_number_hash="")


def apply_client_attention_filter(queryset: QuerySet[Any], attention_filter: str, today: date | None = None) -> QuerySet[Any]:
    today = today or timezone.localdate()
    expiring_cutoff = today + timedelta(days=7)
    wezwanie_types = {DocumentType.WEZWANIE, DocumentType.WEZWANIE.value}

    if attention_filter == "legal_stay":
        return queryset.filter(_legal_stay_attention_q(today)).distinct()
    if attention_filter == "expired_documents":
        return queryset.filter(
            documents__expiry_date__isnull=False,
            documents__expiry_date__lt=today,
            documents__archived_at__isnull=True,
        ).distinct()
    if attention_filter == "expiring_documents":
        return queryset.filter(
            documents__expiry_date__isnull=False,
            documents__expiry_date__gte=today,
            documents__expiry_date__lte=expiring_cutoff,
            documents__archived_at__isnull=True,
        ).distinct()
    if attention_filter == "unverified_documents":
        return queryset.filter(
            documents__verified=False,
            documents__archived_at__isnull=True,
        ).distinct()
    if attention_filter == "overdue_payments":
        return queryset.filter(
            payments__status__in=["pending", "partial"],
            payments__due_date__isnull=False,
            payments__due_date__lte=today,
            payments__archived_at__isnull=True,
        ).distinct()
    if attention_filter == "failed_emails":
        return queryset.filter(email_logs__delivery_status="failed").distinct()
    if attention_filter == "fingerprints_email":
        return queryset.filter(fingerprints_date__isnull=False).exclude(
            email_logs__template_type="appointment_notification",
        ).distinct()
    if attention_filter == "overdue_tasks":
        return queryset.filter(
            staff_tasks__status__in=["open", "in_progress"],
            staff_tasks__due_date__lt=today,
        ).distinct()
    if attention_filter == "wezwanie_missing_case":
        return queryset.filter(
            _missing_case_number_q(),
            documents__document_type__in=wezwanie_types,
            documents__archived_at__isnull=True,
        ).distinct()
    if attention_filter == "new_card_missing_case":
        return queryset.filter(
            _missing_case_number_q(),
            mos_application_data__new_residence_card_application_status="yes",
        ).distinct()
    return queryset


def count_client_attention_filters(queryset: QuerySet[Any], today: date | None = None) -> dict[str, int]:
    today = today or timezone.localdate()
    return {
        attention_filter: apply_client_attention_filter(queryset, attention_filter, today).count()
        for attention_filter in ATTENTION_FILTERS
    }
