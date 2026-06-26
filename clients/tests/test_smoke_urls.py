"""Smoke tests: hit every named URL in the clients app and verify no 500s."""
from __future__ import annotations

import pytest
from django.test import Client as DjangoClient
from django.urls import reverse

from clients.models import Client
from clients.tests.factories import create_staff_user

# URLs that only need a logged-in staff user (no object PKs).
SIMPLE_URLS = [
    "clients:client_list",
    "clients:client_add",
    "clients:admin_panel",
    "clients:metrics_dashboard",
    "clients:task_list",
    "clients:mass_email",
]


@pytest.fixture
def _staff_client(db):
    user = create_staff_user()
    client = DjangoClient()
    client.force_login(user)
    return client, user


@pytest.fixture
def _client_record(db):
    return Client.objects.create(
        first_name="Smoke",
        last_name="Test",
        email="smoke@example.com",
        phone="+48000000000",
        citizenship="Poland",
        application_purpose="work",
    )


@pytest.mark.parametrize("url_name", SIMPLE_URLS)
def test_simple_urls_no_500(url_name, _staff_client):
    http_client, _ = _staff_client
    url = reverse(url_name)
    response = http_client.get(url)
    assert response.status_code != 500, f"{url_name} returned 500"


def test_client_detail_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    url = reverse("clients:client_detail", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_client_edit_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    url = reverse("clients:client_edit", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_client_edit_post_saves_without_500(_staff_client, _client_record):
    # Regression: ClientUpdateView.form_valid must not touch dropped Client
    # process columns (spec §4).
    http_client, _ = _staff_client
    url = reverse("clients:client_edit", kwargs={"pk": _client_record.pk})
    response = http_client.post(
        url,
        {
            "first_name": "Smoke",
            "last_name": "Edited",
            "email": "smoke@example.com",
            "phone": "+48000000001",
            "citizenship": "Poland",
            "application_purpose": "work",
            "language": "pl",
            "status": "new",
            "family_role": "",
            "sponsor_client": "",
            "notes": "edited",
        },
    )
    assert response.status_code != 500
    _client_record.refresh_from_db()
    assert _client_record.last_name == "Edited"


def test_case_detail_no_500(_staff_client, _client_record):
    # Regression: CaseDetailView must not read dropped Client.case_number when a
    # single case has no authority/legacy number yet (spec §4).
    http_client, _ = _staff_client
    case = _client_record.cases.first()
    assert case is not None
    url = reverse("clients:case_detail", kwargs={"pk": case.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_case_add_no_500(_staff_client, _client_record):
    # Regression: CaseCreateView.get_initial must not read dropped
    # Client.workflow_stage (spec §4).
    http_client, _ = _staff_client
    url = reverse("clients:case_add", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_case_edit_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    case = _client_record.cases.first()
    assert case is not None, "primary case should be auto-created"
    url = reverse("clients:case_edit", kwargs={"pk": case.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_case_edit_post_saves_process_data_without_500(_staff_client, _client_record):
    # Regression: process data (case number, dates) now lives on Case (spec §4);
    # CaseUpdateView.form_valid must persist it without touching dropped Client
    # columns or 500ing.
    http_client, _ = _staff_client
    case = _client_record.cases.first()
    assert case is not None
    url = reverse("clients:case_edit", kwargs={"pk": case.pk})
    response = http_client.post(
        url,
        {
            "authority_case_number": "WSC-II-P.6151.000001.2026",
            "application_purpose": "work",
            "application_type": "",
            "basis_of_stay": "",
            "workflow_stage": case.workflow_stage,
            "submission_date": "",
            "fingerprints_date": "",
            "assigned_staff": "",
            "company": "",
            "version": case.version,
        },
    )
    assert response.status_code != 500
    case.refresh_from_db()
    assert case.authority_case_number == "WSC-II-P.6151.000001.2026"


def test_client_print_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    url = reverse("clients:client_print", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_checklist_partial_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    url = reverse("clients:client_checklist_partial", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_overview_partial_no_500(_staff_client, _client_record):
    http_client, _ = _staff_client
    url = reverse("clients:client_overview_partial", kwargs={"pk": _client_record.pk})
    response = http_client.get(url)
    assert response.status_code != 500


def test_unauthenticated_redirects_to_login(db):
    """An anonymous user should be redirected, never get a 500."""
    http_client = DjangoClient()
    url = reverse("clients:client_list")
    response = http_client.get(url)
    assert response.status_code in (301, 302, 403), "Anonymous should not see 200 or 500"
