from __future__ import annotations

import pytest
from django.urls import reverse

from clients.models import Client
from clients.services.cases import create_case_for_client
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_user


@pytest.mark.django_db
def test_case_detail_renders_with_ux_changes(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)

    response = client.get(reverse("clients:case_detail", kwargs={"pk": case.pk}))
    body = response.content.decode()

    assert response.status_code == 200
    # Internal/unwanted fields are gone.
    assert "Версия записи" not in body
    assert "Ответственный" not in body
    # New UX affordances are present.
    assert reverse("clients:add_task", kwargs={"client_id": customer.pk}) in body
    assert reverse("clients:add_payment", kwargs={"client_id": customer.pk}) in body
    assert 'id="historyFilter"' in body
    assert 'id="hideArchivedDocs"' in body
    # Working modals are present on the case page.
    assert 'id="caseAddTaskModal"' in body
    assert 'id="caseAddPaymentModal"' in body


@pytest.mark.django_db
def test_add_payment_returns_to_case_via_next(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)

    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    case = create_case_for_client(client=customer, actor=staff)
    case_url = reverse("clients:case_detail", kwargs={"pk": case.pk})

    response = client.post(
        reverse("clients:add_payment", kwargs={"client_id": customer.pk}),
        data={
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "0",
            "status": "pending",
            "payment_method": "cash",
            "next": case_url,
        },
    )

    assert response.status_code == 302
    assert response.url == case_url


@pytest.mark.django_db
def test_add_payment_rejects_offsite_next(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
    customer = Client.objects.create(first_name="Darya", last_name="A", citizenship="BY")
    create_case_for_client(client=customer, actor=staff)

    response = client.post(
        reverse("clients:add_payment", kwargs={"client_id": customer.pk}),
        data={
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "0",
            "status": "pending",
            "payment_method": "cash",
            "next": "https://evil.example.com/phish",
        },
    )

    assert response.status_code == 302
    # Open-redirect is rejected; falls back to the client page.
    assert "evil.example.com" not in response.url
