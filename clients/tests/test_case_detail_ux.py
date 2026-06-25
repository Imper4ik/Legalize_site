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
