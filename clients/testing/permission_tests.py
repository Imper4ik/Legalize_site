from __future__ import annotations

from django.test import Client as DjangoClient
from django.urls import reverse

from clients.testing.assertions import ScenarioRecorder
from clients.testing.factories import create_test_user


def run_permission_scenarios(recorder: ScenarioRecorder) -> None:
    staff = create_test_user(role="Staff", email="test-center-ordinary-staff@example.test")
    superuser = create_test_user(
        role="Admin",
        email="test-center-superuser@example.test",
        is_superuser=True,
    )

    browser = DjangoClient()
    browser.force_login(staff)
    staff_response = browser.get(reverse("clients:test_center"))
    recorder.check(
        "test_center.ordinary_staff_forbidden",
        staff_response.status_code == 403,
        expected="403",
        actual=f"status={staff_response.status_code}",
    )

    browser.force_login(superuser)
    enabled_response = browser.get(reverse("clients:test_center"))
    recorder.check(
        "test_center.superuser_allowed",
        enabled_response.status_code == 200,
        expected="200 for superuser",
        actual=f"status={enabled_response.status_code}",
    )
