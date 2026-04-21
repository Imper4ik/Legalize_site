from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.http import HttpResponse

from clients.models import Client, ClientActivity, Document, Payment, Reminder
from clients.views.base import staff_required_view


class StaffRequiredViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        user_model = get_user_model()
        self.user = user_model.objects.create_user(email="u@example.com", password="pass", is_staff=False)

    def test_non_staff_ajax_gets_json_forbidden(self):
        @staff_required_view
        def protected(_request):
            return HttpResponse("ok")

        request = self.factory.get("/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        request.user = self.user

        response = protected(request)

        self.assertEqual(response.status_code, 403)
        payload = json.loads(response.content.decode("utf-8"))
        self.assertEqual(payload["status"], "error")


class ClientViewEdgeCaseTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="staff@example.com", password="pass", is_staff=True)
        self.client.login(email="staff@example.com", password="pass")

        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            citizenship="PL",
            phone="+48123123123",
            email="jan-edge@example.com",
        )

    def test_get_price_for_service_returns_success_json(self):
        response = self.client.get(reverse("clients:get_price_for_service", kwargs={"service_value": "study_service"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("price", payload)

    def test_add_payment_ajax_invalid_payload_returns_error(self):
        response = self.client.post(
            reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}),
            data={},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("errors", payload)

    def test_edit_payment_ajax_invalid_payload_returns_error(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="0.00",
        )

        response = self.client.post(
            reverse("clients:edit_payment", kwargs={"payment_id": payment.pk}),
            data={"service_description": "", "total_amount": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertIn("errors", payload)

    def test_delete_payment_ajax_returns_success_payload(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="0.00",
        )

        response = self.client.post(
            reverse("clients:delete_payment", kwargs={"payment_id": payment.pk}),
            data={},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("message", payload)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    @patch("clients.views.reminders.call_command")
    def test_run_update_reminders_post_redirects_to_payments(self, call_cmd):
        response = self.client.post(
            reverse("clients:run_update_reminders"),
            data={"next": "payments"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("clients:payment_reminder_list"), response.url)
        call_cmd.assert_called_once_with("update_reminders")

    def test_reminder_action_deactivate_marks_inactive(self):
        reminder = Reminder.objects.create(
            client=self.client_obj,
            reminder_type="document",
            title="Check docs",
            due_date="2030-01-01",
            is_active=True,
        )

        response = self.client.post(
            reverse("clients:reminder_action", kwargs={"reminder_id": reminder.pk}),
            data={"action": "deactivate"},
        )

        self.assertEqual(response.status_code, 302)
        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)
        self.assertTrue(
            ClientActivity.objects.filter(
                client=self.client_obj,
                event_type="reminder_deactivated",
            ).exists()
        )

    @patch("clients.views.reminders.send_expiring_documents_email", return_value=1)
    def test_send_document_reminder_email_post_uses_service(self, send_mock):
        document = Document.objects.create(
            client=self.client_obj,
            document_type="passport",
            file="documents/test.pdf",
            expiry_date="2030-01-01",
        )
        Reminder.objects.create(
            client=self.client_obj,
            document=document,
            reminder_type="document",
            title="Doc reminder",
            due_date="2030-01-01",
            is_active=True,
        )

        response = self.client.post(
            reverse("clients:send_document_reminder_email", kwargs={"client_id": self.client_obj.pk}),
            data={},
        )

        self.assertEqual(response.status_code, 302)
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertEqual(args[0], self.client_obj)
        self.assertEqual([doc.pk for doc in args[1]], [document.pk])
        self.assertEqual(kwargs["sent_by"], self.staff)

    def test_email_preview_custom_template_returns_empty_payload(self):
        response = self.client.get(
            reverse("clients:email_preview_api", kwargs={"pk": self.client_obj.pk}),
            {"template_type": "custom"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload, {"subject": "", "body": ""})

    def test_delete_payment_get_request_does_not_delete(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="0.00",
        )

        response = self.client.get(reverse("clients:delete_payment", kwargs={"payment_id": payment.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())
