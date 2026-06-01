from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.http import HttpResponse
from django.utils.translation import gettext as _

from clients.models import AppSettings, Client, ClientActivity, Document, MOSApplicationData, Payment, Reminder, ServicePrice, StaffAuditEvent
from clients.services.access import user_has_internal_role
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


class RolePolicyTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.regular = user_model.objects.create_user(
            email="regular@example.com",
            password="pass",
            is_staff=False,
        )
        self.group_only = user_model.objects.create_user(
            email="group@example.com",
            password="pass",
            is_staff=False,
        )
        self.staff_only = user_model.objects.create_user(
            email="staff-only@example.com",
            password="pass",
            is_staff=True,
        )
        self.staff_with_role = user_model.objects.create_user(
            email="staff-role@example.com",
            password="pass",
            is_staff=True,
        )
        admin_group = Group.objects.get(name="Admin")
        self.group_only.groups.add(admin_group)
        self.staff_with_role.groups.add(admin_group)

    def test_regular_user_is_denied(self):
        self.assertFalse(user_has_internal_role(self.regular, "Admin"))

    def test_group_membership_without_staff_flag_is_denied(self):
        self.assertFalse(user_has_internal_role(self.group_only, "Admin"))

    def test_staff_without_required_group_is_denied(self):
        self.assertFalse(user_has_internal_role(self.staff_only, "Admin"))

    def test_staff_with_required_group_is_allowed(self):
        self.assertTrue(user_has_internal_role(self.staff_with_role, "Admin"))


@override_settings(LANGUAGE_CODE="ru")
class ClientViewEdgeCaseTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
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

    def test_completed_onboarding_badge_filters_client_list(self):
        completed_client = Client.objects.create(
            first_name="CompletedClient",
            last_name="Onboarding",
            email="completed-onboarding@example.com",
        )
        MOSApplicationData.objects.update_or_create(
            client=completed_client,
            defaults={"status": "client_completed"},
        )
        review_client = Client.objects.create(
            first_name="ReviewClient",
            last_name="Onboarding",
            email="review-onboarding@example.com",
        )
        MOSApplicationData.objects.update_or_create(
            client=review_client,
            defaults={"status": "staff_review"},
        )
        submitted_client = Client.objects.create(
            first_name="SubmittedClient",
            last_name="Onboarding",
            email="submitted-onboarding@example.com",
        )
        MOSApplicationData.objects.update_or_create(
            client=submitted_client,
            defaults={"status": "submitted_in_mos"},
        )
        draft_client = Client.objects.create(
            first_name="DraftClient",
            last_name="Onboarding",
            email="draft-onboarding@example.com",
        )
        MOSApplicationData.objects.update_or_create(
            client=draft_client,
            defaults={"status": "draft"},
        )

        list_url = reverse("clients:client_list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'{list_url}?onboarding=completed')
        self.assertContains(response, f'{list_url}?onboarding=staff_review')
        self.assertContains(response, f'{list_url}?onboarding=submitted_in_mos')

        filtered_completed = self.client.get(list_url, {"onboarding": "completed"})
        self.assertEqual(filtered_completed.status_code, 200)
        self.assertContains(filtered_completed, "CompletedClient")
        self.assertNotContains(filtered_completed, "ReviewClient")
        self.assertNotContains(filtered_completed, "SubmittedClient")
        self.assertNotContains(filtered_completed, "DraftClient")
        self.assertEqual(filtered_completed.context["onboarding_filter"], "completed")

        filtered_review = self.client.get(list_url, {"onboarding": "staff_review"})
        self.assertEqual(filtered_review.status_code, 200)
        self.assertContains(filtered_review, "ReviewClient")
        self.assertNotContains(filtered_review, "CompletedClient")
        self.assertNotContains(filtered_review, "SubmittedClient")
        self.assertNotContains(filtered_review, "DraftClient")
        self.assertEqual(filtered_review.context["onboarding_filter"], "staff_review")

        filtered_submitted = self.client.get(list_url, {"onboarding": "submitted_in_mos"})
        self.assertEqual(filtered_submitted.status_code, 200)
        self.assertContains(filtered_submitted, "SubmittedClient")
        self.assertNotContains(filtered_submitted, "CompletedClient")
        self.assertNotContains(filtered_submitted, "ReviewClient")
        self.assertNotContains(filtered_submitted, "DraftClient")
        self.assertEqual(filtered_submitted.context["onboarding_filter"], "submitted_in_mos")

    def test_client_attention_menu_and_document_filters_show_ocr_events(self):
        review_client = Client.objects.create(
            first_name="Review",
            last_name="Client",
            email="ocr-review@example.com",
        )
        pending_client = Client.objects.create(
            first_name="Pending",
            last_name="Client",
            email="ocr-pending@example.com",
        )
        warning_client = Client.objects.create(
            first_name="Warning",
            last_name="Client",
            email="ocr-warning@example.com",
        )
        Document.objects.create(
            client=review_client,
            document_type="passport",
            file=SimpleUploadedFile("review.pdf", b"file", content_type="application/pdf"),
            awaiting_confirmation=True,
            ocr_status="success",
        )
        Document.objects.create(
            client=pending_client,
            document_type="passport",
            file=SimpleUploadedFile("pending.pdf", b"file", content_type="application/pdf"),
            ocr_status="pending",
        )
        Document.objects.create(
            client=warning_client,
            document_type="passport",
            file=SimpleUploadedFile("warning.pdf", b"file", content_type="application/pdf"),
            ocr_status="success",
            ocr_name_mismatch=True,
        )

        list_url = reverse("clients:client_list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{list_url}?document=ocr_review")
        self.assertContains(response, f"{list_url}?document=ocr_pending")
        self.assertContains(response, f"{list_url}?document=ocr_warning")
        self.assertEqual(response.context["client_attention_count"], 3)

        filtered_response = self.client.get(list_url, {"document": "ocr_review"})
        self.assertEqual(filtered_response.status_code, 200)
        self.assertContains(filtered_response, "Review")
        self.assertNotContains(filtered_response, "Pending")
        self.assertNotContains(filtered_response, "Warning")
        self.assertEqual(filtered_response.context["document_filter"], "ocr_review")

    def test_get_price_for_service_returns_success_json(self):
        response = self.client.get(reverse("clients:get_price_for_service", kwargs={"service_value": "study_service"}))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("price", payload)

    @override_settings(LANGUAGE_CODE="ru")
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

    def test_staff_manage_update_creates_permission_audit_event(self):
        user_model = get_user_model()
        target = user_model.objects.create_user(
            email="audited-staff@example.com",
            password="pass",
            is_staff=True,
            is_active=True,
        )
        staff_group = Group.objects.get(name="Staff")
        target.groups.add(staff_group)

        response = self.client.post(
            reverse("clients:staff_manage"),
            data={
                "action": "update",
                "user_id": str(target.pk),
                f"user-{target.pk}-email": target.email,
                f"user-{target.pk}-first_name": "Audit",
                f"user-{target.pk}-last_name": "Target",
                f"user-{target.pk}-is_staff": "on",
                f"user-{target.pk}-is_active": "on",
                f"user-{target.pk}-groups": [str(staff_group.pk)],
                f"user-{target.pk}-can_manage_payments": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        event = StaffAuditEvent.objects.get(target=target)
        self.assertEqual(event.actor, self.staff)
        self.assertEqual(event.event_type, StaffAuditEvent.EVENT_STAFF_UPDATED)
        self.assertEqual(
            event.metadata["permission_changes"]["can_manage_payments"],
            {"old": False, "new": True},
        )
        self.assertNotIn(target.email, json.dumps(event.metadata))

    def test_staff_manage_toggle_active_creates_audit_event(self):
        user_model = get_user_model()
        target = user_model.objects.create_user(
            email="toggle-staff@example.com",
            password="pass",
            is_staff=True,
            is_active=True,
        )
        target.groups.add(Group.objects.get(name="Staff"))

        response = self.client.post(
            reverse("clients:staff_manage"),
            data={"action": "toggle_active", "user_id": str(target.pk)},
        )

        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        event = StaffAuditEvent.objects.get(target=target)
        self.assertEqual(event.event_type, StaffAuditEvent.EVENT_STAFF_ACTIVE_TOGGLED)
        self.assertEqual(event.metadata["old"], True)
        self.assertEqual(event.metadata["new"], False)

    def test_staff_manage_renders(self):
        response = self.client.get(reverse("clients:staff_manage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("Сотрудники"))

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


class ObjectAccessPolicyTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.staff_a = user_model.objects.create_user(
            email="staff-a@example.com",
            password="pass",
            is_staff=True,
        )
        self.staff_b = user_model.objects.create_user(
            email="staff-b@example.com",
            password="pass",
            is_staff=True,
        )
        staff_group = Group.objects.get(name="Staff")
        self.staff_a.groups.add(staff_group)
        self.staff_b.groups.add(staff_group)

        self.client_owned = Client.objects.create(
            first_name="Owned",
            last_name="Client",
            citizenship="PL",
            phone="+48111111111",
            email="owned@example.com",
            assigned_staff=self.staff_a,
        )
        self.client_foreign = Client.objects.create(
            first_name="Foreign",
            last_name="Client",
            citizenship="PL",
            phone="+48222222222",
            email="foreign@example.com",
            assigned_staff=self.staff_b,
        )
        self.foreign_payment = Payment.objects.create(
            client=self.client_foreign,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="0.00",
        )
        self.foreign_document = Document.objects.create(
            client=self.client_foreign,
            document_type="passport",
            file="documents/foreign.pdf",
        )

    def test_staff_cannot_open_foreign_client_detail(self):
        self.client.login(email="staff-a@example.com", password="pass")

        response = self.client.get(
            reverse("clients:client_detail", kwargs={"pk": self.client_foreign.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_download_foreign_document(self):
        self.client.login(email="staff-a@example.com", password="pass")

        response = self.client.get(
            reverse("clients:document_download", kwargs={"doc_id": self.foreign_document.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_edit_foreign_payment(self):
        self.client.login(email="staff-a@example.com", password="pass")

        response = self.client.post(
            reverse("clients:edit_payment", kwargs={"payment_id": self.foreign_payment.pk}),
            data={"service_description": "consultation", "total_amount": "150.00"},
        )

        self.assertEqual(response.status_code, 403)

    def test_assigned_staff_can_open_owned_client(self):
        self.client.login(email="staff-a@example.com", password="pass")

        response = self.client.get(
            reverse("clients:client_detail", kwargs={"pk": self.client_owned.pk})
        )

        self.assertEqual(response.status_code, 200)
