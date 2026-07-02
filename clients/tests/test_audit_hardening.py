from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from clients.forms import ClientForm, PaymentForm
from clients.models import Client, ClientActivity, Payment
from clients.services.workflow import validate_case_workflow_transition
from clients.tests.factories import create_manager_user, create_staff_user
from clients.use_cases.client_records import finalize_client_update, snapshot_client_update_state
from clients.use_cases.payments import create_payment_for_client


def _client(**overrides) -> Client:
    defaults = {
        "first_name": "Audit",
        "last_name": "Client",
        "email": "audit-client@example.com",
        "phone": "+48123123123",
        "citizenship": "UA",
        "application_purpose": "work",
        "language": "pl",
    }
    defaults.update(overrides)
    # Staff is no longer assigned to clients (spec §2); ignore any legacy kwarg.
    defaults.pop("assigned_staff", None)
    return Client.objects.create(**defaults)


def _client_form_data(client: Client, **overrides) -> dict[str, str]:
    data = {
        "first_name": client.first_name,
        "last_name": client.last_name,
        "email": client.email,
        "phone": client.phone,
        "citizenship": client.citizenship,
        "birth_date": "",
        "passport_num": "",
        "case_number": "",
        "application_purpose": client.application_purpose,
        "language": client.language,
        "company": "",
        "status": client.status,
        "workflow_stage": "new_client",
        "basis_of_stay": "",
        "legal_basis_end_date": "",
        "submission_date": "",
        "employer_phone": "",
        "fingerprints_date": "",
        "family_role": "",
        "sponsor_client": "",
        "notes": "",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_payment_form_rejects_negative_and_overpaid_amounts():
    negative_form = PaymentForm(
        data={
            "service_description": "consultation",
            "total_amount": "-1.00",
            "amount_paid": "0.00",
            "status": "pending",
            "payment_method": "cash",
        }
    )
    assert not negative_form.is_valid()
    assert "total_amount" in negative_form.errors

    overpaid_form = PaymentForm(
        data={
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "150.00",
            "status": "partial",
            "payment_method": "cash",
        }
    )
    assert not overpaid_form.is_valid()
    assert "amount_paid" in overpaid_form.errors


@pytest.mark.django_db
def test_payment_use_case_rejects_invalid_amounts_before_audit_log():
    staff = create_staff_user()
    client = _client(assigned_staff=staff)

    with pytest.raises(ValidationError):
        create_payment_for_client(
            client=client,
            actor=staff,
            cleaned_data={
                "service_description": "consultation",
                "total_amount": Decimal("100.00"),
                "amount_paid": Decimal("150.00"),
                "status": "partial",
                "payment_method": "cash",
            },
        )

    assert not Payment.objects.filter(client=client).exists()
    assert not ClientActivity.objects.filter(client=client, event_type="payment_created").exists()


@pytest.mark.django_db
def test_payment_database_constraints_block_direct_invalid_writes():
    client = _client()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payment.objects.create(
                client=client,
                service_description="consultation",
                total_amount=Decimal("100.00"),
                amount_paid=Decimal("150.00"),
                status="partial",
            )


@pytest.mark.django_db
def test_limited_staff_client_form_ignores_control_fields_from_post():
    staff = create_staff_user()
    other_staff = create_staff_user()
    client = _client(assigned_staff=staff, status="new", workflow_stage="new_client")

    form = ClientForm(
        data=_client_form_data(
            client,
            assigned_staff=str(other_staff.pk),
            status="approved",
            workflow_stage="closed",
        ),
        instance=client,
        user=staff,
    )

    assert "assigned_staff" not in form.fields
    assert "status" not in form.fields
    assert "workflow_stage" not in form.fields
    assert form.is_valid(), form.errors

    saved = form.save()
    saved.refresh_from_db()
    # Status is a control field limited staff cannot change via POST; it stays "new".
    assert saved.status == "new"


@pytest.mark.django_db
def test_manager_client_form_keeps_control_fields():
    manager = create_manager_user()
    client = _client(assigned_staff=manager)

    form = ClientForm(instance=client, user=manager)

    # Staff is no longer assigned to clients, so the field is gone for everyone (§2).
    assert "assigned_staff" not in form.fields
    assert "status" in form.fields
    # Workflow stage is edited on the case (CaseForm), not on the client (§4).
    assert "workflow_stage" not in form.fields


@pytest.mark.django_db
def test_workflow_cannot_close_with_open_payments():
    client = _client(
        workflow_stage="decision_received",
        decision_date=timezone.localdate(),
    )
    Payment.objects.create(
        client=client,
        service_description="consultation",
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("0.00"),
        status="pending",
    )

    result = validate_case_workflow_transition(
        case=client.cases.get(),
        previous_stage="decision_received",
        next_stage="closed",
    )

    assert not result.allowed


@pytest.mark.django_db
def test_finalize_client_update_does_not_track_workflow():
    # Workflow policy is enforced on the case (CaseForm), not the client update
    # path: finalize no longer validates or logs workflow changes (spec §4).
    staff = create_staff_user()
    client = _client(assigned_staff=staff, workflow_stage="decision_received")
    previous_values = snapshot_client_update_state(client)
    client.workflow_stage = "closed"

    result = finalize_client_update(
        client=client,
        actor=staff,
        previous_values=previous_values,
    )

    assert not result.workflow_changed
    assert "workflow_stage" not in result.changed_fields
    assert not ClientActivity.objects.filter(client=client, event_type="workflow_changed").exists()
