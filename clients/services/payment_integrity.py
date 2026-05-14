from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.db import OperationalError, ProgrammingError, connection
from django.db.models import F, Q, QuerySet

from clients.models import Payment


@dataclass(frozen=True)
class PaymentIntegrityIssue:
    code: str
    label: str
    count: int
    sample_ids: tuple[int, ...]


@dataclass(frozen=True)
class PaymentIntegrityReport:
    checked: bool
    table_missing: bool
    issues: tuple[PaymentIntegrityIssue, ...]

    @property
    def invalid_count(self) -> int:
        return sum(issue.count for issue in self.issues)

    @property
    def is_valid(self) -> bool:
        return self.invalid_count == 0


PAYMENT_INTEGRITY_RULES: tuple[tuple[str, str, Q], ...] = (
    (
        "negative_total_amount",
        "total_amount is negative",
        Q(total_amount__lt=Decimal("0.00")),
    ),
    (
        "negative_amount_paid",
        "amount_paid is negative",
        Q(amount_paid__lt=Decimal("0.00")),
    ),
    (
        "amount_paid_exceeds_total",
        "amount_paid exceeds total_amount",
        Q(amount_paid__gt=F("total_amount")),
    ),
    (
        "pending_has_paid_amount",
        "pending payment has non-zero amount_paid",
        Q(status="pending") & ~Q(amount_paid=Decimal("0.00")),
    ),
    (
        "paid_amount_mismatch",
        "paid payment amount does not match total_amount",
        Q(status="paid") & ~Q(amount_paid=F("total_amount")),
    ),
    (
        "partial_amount_out_of_range",
        "partial payment amount is not between zero and total_amount",
        Q(status="partial")
        & (Q(amount_paid__lte=Decimal("0.00")) | Q(amount_paid__gte=F("total_amount"))),
    ),
)


def _payment_table_exists() -> bool:
    return Payment._meta.db_table in connection.introspection.table_names()


def _sample_ids(queryset: QuerySet[Payment], *, limit: int) -> tuple[int, ...]:
    return tuple(
        queryset.order_by("pk").values_list("pk", flat=True)[:limit]
    )


def audit_payment_integrity(*, sample_limit: int = 20) -> PaymentIntegrityReport:
    if not _payment_table_exists():
        return PaymentIntegrityReport(checked=False, table_missing=True, issues=())

    issues: list[PaymentIntegrityIssue] = []
    base_queryset = Payment.all_objects.all()
    try:
        for code, label, condition in PAYMENT_INTEGRITY_RULES:
            queryset = base_queryset.filter(condition)
            count = queryset.count()
            if count:
                issues.append(
                    PaymentIntegrityIssue(
                        code=code,
                        label=label,
                        count=count,
                        sample_ids=_sample_ids(queryset, limit=sample_limit),
                    )
                )
    except (OperationalError, ProgrammingError):
        return PaymentIntegrityReport(checked=False, table_missing=True, issues=())

    return PaymentIntegrityReport(
        checked=True,
        table_missing=False,
        issues=tuple(issues),
    )


def payment_integrity_report_as_dict(report: PaymentIntegrityReport) -> dict[str, Any]:
    return {
        "checked": report.checked,
        "table_missing": report.table_missing,
        "invalid_count": report.invalid_count,
        "issues": [
            {
                "code": issue.code,
                "label": issue.label,
                "count": issue.count,
                "sample_ids": list(issue.sample_ids),
            }
            for issue in report.issues
        ],
    }
