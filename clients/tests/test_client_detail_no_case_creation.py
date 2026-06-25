from __future__ import annotations

import pytest
from django.urls import reverse

from clients.models import Case, Client
from clients.services.cases import create_case_for_client
from clients.testing.factories import TEST_USER_CREDENTIAL, create_test_user


@pytest.fixture
def staff_client(client):
    staff = create_test_user(role="Manager")
    client.login(email=staff.email, password=TEST_USER_CREDENTIAL)
    return client, staff


@pytest.mark.django_db
def test_view_client_with_single_active_case_redirects_to_it(staff_client):
    client, _staff = staff_client
    customer = Client.objects.create(first_name="One", last_name="Case", citizenship="UA")
    case = Case.objects.filter(client=customer).get()

    response = client.get(reverse("clients:client_detail", kwargs={"pk": customer.pk}))

    assert response.status_code == 302
    assert response.url == reverse("clients:case_detail", kwargs={"pk": case.pk})


@pytest.mark.django_db
def test_view_client_with_archived_only_case_does_not_create_or_redirect(staff_client):
    client, _staff = staff_client
    customer = Client.objects.create(first_name="Arch", last_name="Only", citizenship="UA")
    Case.objects.filter(client=customer).get().archive(save=True)

    before = Case.all_objects.filter(client=customer).count()
    response = client.get(reverse("clients:client_detail", kwargs={"pk": customer.pk}))

    assert response.status_code == 200  # person view, no redirect/500
    assert Case.all_objects.filter(client=customer).count() == before  # no new case


@pytest.mark.django_db
def test_view_client_with_several_active_cases_does_not_create_or_redirect(staff_client):
    client, staff = staff_client
    customer = Client.objects.create(first_name="Multi", last_name="Case", citizenship="UA")
    create_case_for_client(client=customer, actor=staff)  # now two active cases

    before = Case.all_objects.filter(client=customer).count()
    response = client.get(reverse("clients:client_detail", kwargs={"pk": customer.pk}))

    assert response.status_code == 200  # ambiguous -> person view, never guesses
    assert Case.all_objects.filter(client=customer).count() == before
