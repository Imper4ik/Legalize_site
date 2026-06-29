"""Regression tests for Test Center / test-data cleanup.

A test Client always gets an auto-created primary Case (post_save signal), and
``Case.client`` is PROTECT, so cleanup must remove case-scoped children and the
Cases before deleting Clients. Before the fix, ``cleanup_test_data`` deleted
documents/payments and then Clients directly, raising ProtectedError.
"""
from __future__ import annotations

import pytest

from clients.models import Case, Client, Document, Payment, Reminder, StaffTask
from clients.testing.cleanup import cleanup_test_data


@pytest.mark.django_db
def test_cleanup_removes_test_client_with_case_and_children():
    client = Client.objects.create(
        first_name="Cleanup",
        last_name="Target",
        email="test-center-cleanup@example.test",
        application_purpose="work",
        is_test_data=True,
    )
    # The post_save signal created the primary case.
    case = Case.objects.filter(client=client).first()
    assert case is not None

    Document.objects.create(client=client, case=case, document_type="passport", file="documents/x.pdf", is_test_data=True)
    Payment.objects.create(client=client, case=case, service_description="work_service", total_amount=100, is_test_data=True)
    StaffTask.objects.create(client=client, case=case, title="t", due_date="2026-01-01")
    Reminder.objects.create(client=client, case=case, title="r", due_date="2026-01-01", reminder_type="other")

    report = cleanup_test_data(include_test_runs=True)

    # Nothing test-flagged should remain, and no ProtectedError was raised.
    assert not Client.all_objects.filter(is_test_data=True).exists()
    assert not Case.all_objects.filter(client_id=client.pk).exists()
    assert not Document.all_objects.filter(client_id=client.pk).exists()
    assert not Payment.all_objects.filter(client_id=client.pk).exists()
    assert report.deleted.get("clients", 0) >= 1
    assert report.deleted.get("cases", 0) >= 1


@pytest.mark.django_db
def test_cleanup_leaves_real_clients_untouched():
    real = Client.objects.create(
        first_name="Real",
        last_name="Client",
        email="real@example.com",
        application_purpose="work",
        is_test_data=False,
    )
    cleanup_test_data(include_test_runs=True)
    assert Client.all_objects.filter(pk=real.pk).exists()
    assert Case.all_objects.filter(client_id=real.pk).exists()
