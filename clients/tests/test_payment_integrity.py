from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command

from clients.models import Client, Payment
from clients.services.payment_integrity import (
    PaymentIntegrityIssue,
    PaymentIntegrityReport,
    audit_payment_integrity,
)


@pytest.mark.django_db
def test_payment_integrity_audit_passes_for_valid_rows():
    client = Client.objects.create(
        first_name="Valid",
        last_name="Payment",
        email="valid-payment@example.com",
        phone="+48123123123",
        citizenship="UA",
    )
    Payment.objects.create(
        client=client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        status="pending",
    )

    report = audit_payment_integrity()

    assert report.checked
    assert not report.table_missing
    assert report.is_valid


@pytest.mark.django_db
def test_audit_payment_integrity_command_outputs_success_for_clean_database():
    out = StringIO()

    call_command("audit_payment_integrity", stdout=out)

    assert "Payment integrity audit passed" in out.getvalue()


@pytest.mark.django_db
@patch("clients.management.commands.audit_payment_integrity.audit_payment_integrity")
def test_audit_payment_integrity_command_fails_for_invalid_rows(audit_mock):
    audit_mock.return_value = PaymentIntegrityReport(
        checked=True,
        table_missing=False,
        issues=(
            PaymentIntegrityIssue(
                code="amount_paid_exceeds_total",
                label="amount_paid exceeds total_amount",
                count=2,
                sample_ids=(10, 11),
            ),
        ),
    )
    err = StringIO()

    with pytest.raises(CommandError):
        call_command("audit_payment_integrity", stderr=err)

    assert "amount_paid_exceeds_total" in err.getvalue()
    assert "10, 11" in err.getvalue()


@pytest.mark.django_db
@patch("clients.management.commands.audit_payment_integrity.audit_payment_integrity")
def test_audit_payment_integrity_command_warn_only_does_not_raise(audit_mock):
    audit_mock.return_value = PaymentIntegrityReport(
        checked=True,
        table_missing=False,
        issues=(
            PaymentIntegrityIssue(
                code="pending_has_paid_amount",
                label="pending payment has non-zero amount_paid",
                count=1,
                sample_ids=(42,),
            ),
        ),
    )
    out = StringIO()

    call_command("audit_payment_integrity", "--warn-only", stdout=out)

    assert "Payment integrity audit failed" in out.getvalue()
