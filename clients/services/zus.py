from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from django.utils import timezone
from django.core.exceptions import ValidationError

from clients.constants import DocumentType

if TYPE_CHECKING:
    from clients.models import Client, Case

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


def _resolve_to_case(obj: Case | Client, func_name: str) -> Case:
    from clients.models import Case, Client
    if isinstance(obj, Case):
        return obj
    # Deprecated fallback using compatibility helper
    from clients.services.cases import get_legacy_compatibility_case
    return get_legacy_compatibility_case(obj.pk, func_name)


def uploaded_zus_months(case_or_client: Case | Client) -> set[date]:
    case = _resolve_to_case(case_or_client, "uploaded_zus_months")
    return {
        month_start(value)
        for value in case.documents.filter(
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            zus_period_month__isnull=False,
            verified=True,
            archived_at__isnull=True,
        ).values_list("zus_period_month", flat=True)
        if value
    }


def missing_zus_months(case_or_client: Case | Client, *, today: date | None = None) -> list[date]:
    case = _resolve_to_case(case_or_client, "missing_zus_months")
    today = today or timezone.localdate()
    if getattr(case, "workflow_stage", None) != "waiting_decision":
        return []
    if not case.fingerprints_date or case.fingerprints_date > today:
        return []
    if getattr(case, "decision_date", None):
        return []

    expected = expected_zus_months(case.fingerprints_date, today=today)
    insurance_expiry = latest_health_insurance_expiry(case)
    if insurance_expiry:
        covered_until = month_start(insurance_expiry)
        expected = [month for month in expected if month > covered_until]
    uploaded = uploaded_zus_months(case)
    missing = [month for month in expected if month not in uploaded]
    if missing:
        logger.info(
            "ZUS RCA missing months: case_id=%s client_id=%s months=%s",
            case.pk,
            case.client_id,
            [month.isoformat() for month in missing],
        )
    return missing


def latest_health_insurance_expiry(case_or_client: Case | Client) -> date | None:
    case = _resolve_to_case(case_or_client, "latest_health_insurance_expiry")
    return case.documents.filter(
        document_type=DocumentType.HEALTH_INSURANCE.value,
        expiry_date__isnull=False,
        archived_at__isnull=True,
        verified=True,
    ).order_by("-expiry_date").values_list("expiry_date", flat=True).first()


def format_zus_months(months: list[date]) -> str:
    return ", ".join(month.strftime("%m.%Y") for month in months)


def missing_zus_month_upload_options(case_or_client: Case | Client, *, today: date | None = None) -> list[dict[str, str]]:
    case = _resolve_to_case(case_or_client, "missing_zus_month_upload_options")
    return [
        {
            "value": month.isoformat(),
            "label": month.strftime("%m.%Y"),
        }
        for month in missing_zus_months(case, today=today)
    ]
