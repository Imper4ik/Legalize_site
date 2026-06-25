from __future__ import annotations

import pytest
from django.urls import reverse

from clients.models import Client
from clients.models.permissions import EmployeePermission
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_user


@pytest.fixture
def staff_client(client):
    staff = create_test_user(role="Staff")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
    return client, staff


@pytest.mark.django_db
def test_staff_cannot_access_settings_templates_or_logs(staff_client):
    client, _staff = staff_client
    for url_name in ("document_template_hub", "email_logs", "staff_activity_logs"):
        resp = client.get(reverse(f"clients:{url_name}"))
        assert resp.status_code == 403, url_name


@pytest.mark.django_db
def test_staff_keeps_reports_and_dashboard(staff_client):
    client, _staff = staff_client
    assert client.get(reverse("clients:metrics_dashboard")).status_code == 200
    assert client.get(reverse("clients:admin_dashboard")).status_code == 200


@pytest.mark.django_db
def test_staff_cannot_delete_by_default(staff_client):
    client, _staff = staff_client
    customer = Client.objects.create(first_name="X", last_name="Y", citizenship="UA")
    assert client.get(reverse("clients:client_delete", kwargs={"pk": customer.pk})).status_code == 403


@pytest.mark.django_db
def test_admin_can_grant_delete_to_staff(staff_client):
    client, staff = staff_client
    EmployeePermission.objects.update_or_create(
        user=staff, defaults={"can_delete_clients": True}
    )
    customer = Client.objects.create(first_name="X", last_name="Y", citizenship="UA")
    # With the admin-granted per-employee flag the confirm page is reachable.
    assert client.get(reverse("clients:client_delete", kwargs={"pk": customer.pk})).status_code == 200


@pytest.mark.django_db
def test_staff_can_still_edit_clients(staff_client):
    client, _staff = staff_client
    customer = Client.objects.create(first_name="X", last_name="Y", citizenship="UA")
    assert client.get(reverse("clients:client_edit", kwargs={"pk": customer.pk})).status_code == 200
