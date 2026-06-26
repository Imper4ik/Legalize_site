from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, TypeAlias

from django.utils import timezone

from clients.constants import DocumentType

if TYPE_CHECKING:
    from clients.models.case import Case

    # ZUS computation is case-first (spec §4): the workflow stage, fingerprints
    # date, decision date and documents are all read from the Case.
    ZusSubject: TypeAlias = "Case"

logger = logging.getLogger(__name__)


def month_start(value: date) -> date:
    return value.replace(day=1)


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def iter_months(start: date, end: date) -> list[date]:
    if start > end:
        return []

    months: list[date] = []
    current = month_start(start)
    end = month_start(end)
    while current <= end:
        months.append(current)
        current = add_months(current, 1)
    return months


def expected_zus_months(fingerprints_date: date | None, *, today: date | None = None) -> list[date]:
    if not fingerprints_date:
        return []

    today = today or timezone.localdate()
    if fingerprints_date > today:
        return []
    fingerprints_month = month_start(fingerprints_date)
    # Require the two months before fingerprints, the fingerprints month, and later available months.
    first_expected = add_months(fingerprints_month, -2)
    # ZUS RCA for the previous month is considered available from the 17th day.
    last_expected = add_months(month_start(today), -1 if today.day >= 17 else -2)
    return iter_months(first_expected, last_expected)


def uploaded_zus_months(subject: "ZusSubject") -> set[date]:
    return {
        month_start(value)
        for value in subject.documents.filter(
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            zus_period_month__isnull=False,
            verified=True,
            archived_at__isnull=True,
        ).values_list("zus_period_month", flat=True)
        if value
    }


def missing_zus_months(subject: "ZusSubject", *, today: date | None = None) -> list[date]:
    today = today or timezone.localdate()
    if getattr(subject, "workflow_stage", None) != "waiting_decision":
        return []
    if not subject.fingerprints_date or subject.fingerprints_date > today:
        return []
    if getattr(subject, "decision_date", None):
        return []

    expected = expected_zus_months(subject.fingerprints_date, today=today)
    insurance_expiry = latest_health_insurance_expiry(subject)
    if insurance_expiry:
        covered_until = month_start(insurance_expiry)
        expected = [month for month in expected if month > covered_until]
    uploaded = uploaded_zus_months(subject)
    missing = [month for month in expected if month not in uploaded]
    if missing:
        logger.info(
            "ZUS RCA missing months: subject_pk=%s months=%s",
            subject.pk,
            [month.isoformat() for month in missing],
        )
    return missing


def latest_health_insurance_expiry(subject: "ZusSubject") -> date | None:
    return subject.documents.filter(
        document_type=DocumentType.HEALTH_INSURANCE.value,
        expiry_date__isnull=False,
        archived_at__isnull=True,
        verified=True,
    ).order_by("-expiry_date").values_list("expiry_date", flat=True).first()


def format_zus_months(months: list[date]) -> str:
    return ", ".join(month.strftime("%m.%Y") for month in months)


def missing_zus_month_upload_options(subject: "ZusSubject", *, today: date | None = None) -> list[dict[str, str]]:
    return [
        {
            "value": month.isoformat(),
            "label": month.strftime("%m.%Y"),
        }
        for month in missing_zus_months(subject, today=today)
    ]
