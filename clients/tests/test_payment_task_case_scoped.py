"""spec §6: payments and tasks are created against the concrete open case.

A multi-case client must not fall back to an arbitrary case, and a payment/task
can never be attached to another client's case.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from clients.models import Payment, StaffTask
from clients.services.cases import create_case_for_client
from clients.testing.factories import (
    TEST_USER_CREDENTIAL,
    create_test_client,
    create_test_user,
)


class PaymentTaskCaseScopedTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client_obj = create_test_client(first_name="Multi", last_name="Case")
        self.case_a = self.client_obj.cases.get()
        self.case_b = create_case_for_client(client=self.client_obj, actor=self.staff)
        self.http = self.client
        self.http.login(email=self.staff.email, password=TEST_USER_CREDENTIAL)

    def _payment_payload(self, case_uuid: str | None) -> dict[str, str]:
        data = {
            "service_description": "consultation",
            "total_amount": "100.00",
            "amount_paid": "0.00",
            "status": "pending",
            "payment_method": "cash",
        }
        if case_uuid is not None:
            data["case_uuid"] = case_uuid
        return data

    def _task_payload(self, case_uuid: str | None) -> dict[str, str]:
        data = {
            "title": "Follow up",
            "description": "",
            "status": "open",
            "priority": "high",
            "assignee": str(self.staff.pk),
        }
        if case_uuid is not None:
            data["case_uuid"] = case_uuid
        return data

    def test_payment_from_case_a_is_attached_to_case_a(self) -> None:
        resp = self.http.post(
            reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}),
            self._payment_payload(str(self.case_a.uuid)),
        )
        self.assertin_redirect(resp)
        payment = Payment.objects.get(client=self.client_obj)
        self.assertEqual(payment.case_id, self.case_a.id)

    def test_task_from_case_b_is_attached_to_case_b(self) -> None:
        resp = self.http.post(
            reverse("clients:add_task", kwargs={"client_id": self.client_obj.pk}),
            self._task_payload(str(self.case_b.uuid)),
        )
        self.assertin_redirect(resp)
        task = StaffTask.objects.get(client=self.client_obj, title="Follow up")
        self.assertEqual(task.case_id, self.case_b.id)

    def test_payment_for_foreign_clients_case_is_refused(self) -> None:
        other_client = create_test_client(first_name="Other", last_name="Client")
        other_case = other_client.cases.get()
        resp = self.http.post(
            reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}),
            self._payment_payload(str(other_case.uuid)),
        )
        self.assertin_redirect(resp)
        # No payment was created against either client.
        self.assertFalse(Payment.objects.filter(client=self.client_obj).exists())
        self.assertFalse(Payment.objects.filter(client=other_client).exists())

    def test_task_for_archived_case_is_refused(self) -> None:
        from clients.services.archive import archive_case

        archive_case(case=self.case_b, actor=self.staff)
        resp = self.http.post(
            reverse("clients:add_task", kwargs={"client_id": self.client_obj.pk}),
            self._task_payload(str(self.case_b.uuid)),
        )
        self.assertin_redirect(resp)
        self.assertFalse(StaffTask.objects.filter(client=self.client_obj, title="Follow up").exists())

    def test_other_staff_sees_payment_created_from_a_case(self) -> None:
        self.http.post(
            reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}),
            self._payment_payload(str(self.case_a.uuid)),
        )
        other_staff = create_test_user(role="Staff", email="other-staff-scoped@example.com")
        self.http.logout()
        self.http.login(email=other_staff.email, password=TEST_USER_CREDENTIAL)
        detail = self.http.get(reverse("clients:case_detail", kwargs={"pk": self.case_a.pk}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["payments"].count(), 1)

    # --- helper ---------------------------------------------------------
    def assertin_redirect(self, response) -> None:  # noqa: N802
        self.assertIn(response.status_code, (302, 303))
