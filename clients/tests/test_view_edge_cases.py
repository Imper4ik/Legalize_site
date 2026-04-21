from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.http import HttpResponse

from clients.models import AppSettings, Client, ClientActivity, Document, Payment, Reminder, ServicePrice
from clients.services.roles import ensure_predefined_roles
from clients.views.base import staff_required_view
from submissions.models import Submission


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
        ensure_predefined_roles()
        self.staff.groups.add(Group.objects.get(name="Admin"))
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

    def test_admin_panel_renders_for_staff(self):
        response = self.client.get(reverse("clients:admin_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Админ панель")
        self.assertContains(response, "Цены и услуги")

    def test_service_price_manage_post_saves_prices(self):
        response = self.client.post(
            reverse("clients:service_price_manage"),
            data={
                "work_service-service_code": "work_service",
                "work_service-price": "456.00",
                "study_service-service_code": "study_service",
                "study_service-price": "321.00",
                "consultation-service_code": "consultation",
                "consultation-price": "123.45",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ServicePrice.objects.filter(service_code="consultation", price="123.45").exists())
        self.assertTrue(ServicePrice.objects.filter(service_code="work_service", price="456.00").exists())

    def test_submission_manage_create_creates_submission(self):
        response = self.client.post(
            reverse("clients:submission_manage"),
            data={
                "action": "create",
                "create-name": "Nowa podstawa",
                "create-name_pl": "Nowa podstawa PL",
                "create-name_en": "New basis",
                "create-name_ru": "Новая основа",
                "create-status": "draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(name="Nowa podstawa", status="draft").exists())

    def test_submission_manage_update_updates_submission(self):
        submission = Submission.objects.create(name="Old basis", status="draft")

        response = self.client.post(
            reverse("clients:submission_manage"),
            data={
                "action": "update",
                "submission_id": str(submission.id),
                f"submission-{submission.id}-name": "Updated basis",
                f"submission-{submission.id}-name_pl": "Updated PL",
                f"submission-{submission.id}-name_en": "Updated EN",
                f"submission-{submission.id}-name_ru": "Updated RU",
                f"submission-{submission.id}-status": "completed",
            },
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.name, "Updated basis")
        self.assertEqual(submission.status, "completed")

    def test_app_settings_page_saves_general_base_settings(self):
        response = self.client.post(
            reverse("clients:app_settings"),
            data={
                "organization_name": "Legalize Warsaw",
                "contact_email": "office@example.com",
                "contact_phone": "+48123456789",
                "office_address": "UL. TESTOWA 1\n00-001 WARSZAWA",
                "default_proxy_name": "Jan Kowalski",
                "mazowiecki_office_template": "",
                "mazowiecki_proxy_template": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        settings_obj = AppSettings.get_solo()
        self.assertEqual(settings_obj.organization_name, "Legalize Warsaw")
        self.assertEqual(settings_obj.contact_email, "office@example.com")
        self.assertEqual(settings_obj.default_proxy_name, "Jan Kowalski")

    def test_document_template_hub_renders(self):
        response = self.client.get(reverse("clients:document_template_hub"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Шаблоны документов")

    def test_staff_manage_create_creates_staff_user(self):
        response = self.client.post(
            reverse("clients:staff_manage"),
            data={
                "action": "create",
                "create-email": "newstaff@example.com",
                "create-first_name": "Anna",
                "create-last_name": "Nowak",
                "create-password1": "strong-pass-123",
                "create-password2": "strong-pass-123",
                "create-is_staff": "on",
                "create-is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        User = get_user_model()
        self.assertTrue(User.objects.filter(email="newstaff@example.com", is_staff=True).exists())

    def test_staff_manage_renders(self):
        response = self.client.get(reverse("clients:staff_manage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сотрудники")

    def test_role_manage_renders_and_syncs_roles(self):
        response = self.client.get(reverse("clients:role_manage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Роли и доступ")
        self.assertContains(response, "Admin")

        post_response = self.client.post(reverse("clients:role_manage"))
        self.assertEqual(post_response.status_code, 302)

    def test_staff_role_cannot_open_manager_only_sections(self):
        user_model = get_user_model()
        limited_staff = user_model.objects.create_user(
            email="limited@example.com",
            password="pass",
            is_staff=True,
        )
        limited_staff.groups.add(Group.objects.get(name="Staff"))
        self.client.login(email="limited@example.com", password="pass")

        self.assertEqual(self.client.get(reverse("clients:app_settings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:service_price_manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:submission_manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:document_template_hub")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:staff_manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:role_manage")).status_code, 403)

    def test_staff_role_admin_panel_hides_restricted_cards(self):
        user_model = get_user_model()
        limited_staff = user_model.objects.create_user(
            email="staff-panel@example.com",
            password="pass",
            is_staff=True,
        )
        limited_staff.groups.add(Group.objects.get(name="Staff"))
        self.client.login(email="staff-panel@example.com", password="pass")

        response = self.client.get(reverse("clients:admin_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("clients:document_template_hub"))
        self.assertNotContains(response, reverse("clients:submission_manage"))
        self.assertNotContains(response, reverse("clients:service_price_manage"))
        self.assertNotContains(response, reverse("clients:staff_manage"))
        self.assertContains(response, reverse("clients:metrics_dashboard"))

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
