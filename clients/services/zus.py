from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING

from django.utils import timezone

from clients.constants import DocumentType

if TYPE_CHECKING:
    from clients.models.client import Client

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
    first_expected = add_months(month_start(fingerprints_date), 1)
    # ZUS RCA for previous month is usually available after 15th
    last_expected = add_months(month_start(today), -1 if today.day >= 15 else -2)
    return iter_months(first_expected, last_expected)


def uploaded_zus_months(client: Client) -> set[date]:
    return {
        month_start(value)
        for value in client.documents.filter(
            document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
            zus_period_month__isnull=False,
        ).values_list("zus_period_month", flat=True)
        if value
    }


def missing_zus_months(client: Client, *, today: date | None = None) -> list[date]:
    today = today or timezone.localdate()
    if getattr(client, "workflow_stage", None) != "waiting_decision":
        return []
    if not client.fingerprints_date or client.fingerprints_date > today:
        return []
    if getattr(client, "decision_date", None):
        return []

    expected = expected_zus_months(client.fingerprints_date, today=today)
    uploaded = uploaded_zus_months(client)
    missing = [month for month in expected if month not in uploaded]
    if missing:
        logger.info(
            "ZUS RCA missing months: client_id=%s months=%s",
            client.pk,
            [month.isoformat() for month in missing],
        )
    return missing


def format_zus_months(months: list[date]) -> str:
    return ", ".join(month.strftime("%m.%Y") for month in months)


def missing_zus_month_upload_options(client: Client, *, today: date | None = None) -> list[dict[str, str]]:
    return [
        {
            "value": month.isoformat(),
            "label": month.strftime("%m.%Y"),
        }
        for month in missing_zus_months(client, today=today)
    ]
