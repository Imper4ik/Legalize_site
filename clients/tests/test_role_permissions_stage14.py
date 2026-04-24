from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from clients.models import Client, Payment
from clients.services.roles import ensure_predefined_roles


class RolePermissionMatrixTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()

        self.read_only = user_model.objects.create_user(email="readonly@example.com", password="pass", is_staff=True)
        self.staff = user_model.objects.create_user(email="staff@example.com", password="pass", is_staff=True)
        self.manager = user_model.objects.create_user(email="manager@example.com", password="pass", is_staff=True)
        self.admin = user_model.objects.create_user(email="admin@example.com", password="pass", is_staff=True)

        self.read_only.groups.add(Group.objects.get(name="ReadOnly"))
        self.staff.groups.add(Group.objects.get(name="Staff"))
        self.manager.groups.add(Group.objects.get(name="Manager"))
        self.admin.groups.add(Group.objects.get(name="Admin"))

        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            citizenship="PL",
            phone="+48123123123",
            email="jan@example.com",
            assigned_staff=self.staff,
        )
        self.payment = Payment.objects.create(client=self.client_obj, total_amount=10, amount_paid=0, service_description="consultation", payment_method="cash")

    def test_readonly_cannot_mutate_client_data(self):
        self.client.force_login(self.read_only)
        self.assertEqual(self.client.get(reverse("clients:client_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:client_edit", kwargs={"pk": self.client_obj.pk})).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:client_delete", kwargs={"pk": self.client_obj.pk})).status_code, 403)

    def test_readonly_cannot_mutate_documents_exports_emails_payments(self):
        self.client.force_login(self.read_only)
        self.assertEqual(
            self.client.post(reverse("clients:add_document", kwargs={"client_id": self.client_obj.pk, "doc_type": "passport"})).status_code,
            403,
        )
        self.assertEqual(self.client.post(reverse("clients:document_delete", kwargs={"pk": 99999})).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:client_export_zip", kwargs={"pk": self.client_obj.pk})).status_code, 403)
        self.assertEqual(self.client.post(reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk})).status_code, 403)
        self.assertEqual(self.client.post(reverse("clients:edit_payment", kwargs={"payment_id": self.payment.pk})).status_code, 403)

    def test_staff_cannot_access_people_and_settings_management(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("clients:staff_manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:role_manage")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:app_settings")).status_code, 403)
        self.assertEqual(self.client.get(reverse("clients:service_price_manage")).status_code, 403)

    @patch("clients.views.emails.send_mail", return_value=1)
    def test_manager_can_manage_payments_emails_reports(self, _send_mail):
        self.client.force_login(self.manager)
        self.assertEqual(
            self.client.post(reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}), data={"total_amount": "15", "amount_paid": "0", "service_description": "consultation", "status": "pending", "payment_method": "cash"}).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                reverse("clients:send_custom_email", kwargs={"pk": self.client_obj.pk}),
                data={"subject": "Hello", "body": "Test body"},
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get(reverse("clients:client_export_zip", kwargs={"pk": self.client_obj.pk})).status_code, 200)

    def test_admin_can_manage_staff_roles_and_settings(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("clients:staff_manage")).status_code, 200)
        self.assertEqual(self.client.get(reverse("clients:role_manage")).status_code, 200)
        self.assertEqual(self.client.get(reverse("clients:app_settings")).status_code, 200)

    def test_anonymous_is_redirected_from_protected_view(self):
        response = self.client.get(reverse("clients:client_list"))
        self.assertEqual(response.status_code, 302)
