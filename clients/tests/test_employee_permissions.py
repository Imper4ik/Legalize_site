from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Client, Document, EmployeePermission
from clients.services.permissions import has_employee_permission
from clients.services.roles import ensure_predefined_roles


class EmployeePermissionsTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()

        self.staff = user_model.objects.create_user(email="staff-perm@example.com", password="pass", is_staff=True)
        self.staff.groups.add(Group.objects.get(name="Staff"))

        self.admin = user_model.objects.create_user(email="admin-perm@example.com", password="pass", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Admin"))
        self.read_only = user_model.objects.create_user(email="readonly-perm@example.com", password="pass", is_staff=True)
        self.read_only.groups.add(Group.objects.get(name="ReadOnly"))

        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Nowak",
            citizenship="PL",
            phone="+48123123123",
            email="jan.nowak@example.com",
            assigned_staff=self.staff,
        )
        self.document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file=SimpleUploadedFile("passport-perm.pdf", b"passport", content_type="application/pdf"),
        )

    def test_employee_permission_is_auto_created_for_staff_user(self):
        self.assertTrue(EmployeePermission.objects.filter(user=self.staff).exists())

    def test_non_staff_user_does_not_get_employee_permission(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(email="plain-user@example.com", password="pass", is_staff=False)
        self.assertFalse(EmployeePermission.objects.filter(user=user).exists())

    def test_employee_permission_created_when_user_becomes_staff(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(email="promoted-user@example.com", password="pass", is_staff=False)
        self.assertFalse(EmployeePermission.objects.filter(user=user).exists())

        user.is_staff = True
        user.save(update_fields=["is_staff"])

        self.assertTrue(EmployeePermission.objects.filter(user=user).exists())

    def test_has_employee_permission_rules(self):
        self.assertFalse(has_employee_permission(AnonymousUser(), "can_delete_clients"))
        self.assertTrue(has_employee_permission(self.admin, "can_delete_clients"))
        self.assertFalse(has_employee_permission(self.staff, "missing_permission_name"))
        self.assertFalse(has_employee_permission(self.staff, "can_delete_clients"))

    def test_staff_can_delete_client_when_feature_permission_enabled(self):
        perms = self.staff.employee_permission
        perms.can_delete_clients = True
        perms.save(update_fields=["can_delete_clients", "updated_at"])

        self.client.force_login(self.staff)
        response = self.client.post(reverse("clients:client_delete", kwargs={"pk": self.client_obj.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Client.objects.filter(pk=self.client_obj.pk).exists())

    def test_staff_can_delete_document_when_feature_permission_enabled(self):
        perms = self.staff.employee_permission
        perms.can_delete_documents = True
        perms.save(update_fields=["can_delete_documents", "updated_at"])

        self.client.force_login(self.staff)
        response = self.client.post(reverse("clients:document_delete", kwargs={"pk": self.document.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())

    def test_staff_can_manage_checklists_when_feature_permission_enabled(self):
        perms = self.staff.employee_permission
        perms.can_manage_checklists = True
        perms.save(update_fields=["can_manage_checklists", "updated_at"])

        self.client.force_login(self.staff)
        response = self.client.get(reverse("clients:document_checklist_manage"))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_manage_payments_when_feature_permission_enabled(self):
        perms = self.staff.employee_permission
        perms.can_manage_payments = True
        perms.save(update_fields=["can_manage_payments", "updated_at"])

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("clients:add_payment", kwargs={"client_id": self.client_obj.pk}),
            data={
                "total_amount": "100",
                "amount_paid": "0",
                "service_description": "consultation",
                "status": "pending",
                "payment_method": "cash",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_readonly_with_can_delete_clients_still_cannot_delete_client(self):
        perms = self.read_only.employee_permission
        perms.can_delete_clients = True
        perms.save(update_fields=["can_delete_clients", "updated_at"])

        self.client.force_login(self.read_only)
        response = self.client.post(reverse("clients:client_delete", kwargs={"pk": self.client_obj.pk}))
        self.assertEqual(response.status_code, 403)

    def test_readonly_with_can_delete_documents_still_cannot_delete_document(self):
        perms = self.read_only.employee_permission
        perms.can_delete_documents = True
        perms.save(update_fields=["can_delete_documents", "updated_at"])

        self.client.force_login(self.read_only)
        response = self.client.post(reverse("clients:document_delete", kwargs={"pk": self.document.pk}))
        self.assertEqual(response.status_code, 403)

    def test_readonly_with_can_export_clients_still_cannot_export(self):
        perms = self.read_only.employee_permission
        perms.can_export_clients = True
        perms.save(update_fields=["can_export_clients", "updated_at"])

        self.client.force_login(self.read_only)
        response = self.client.get(reverse("clients:client_export_zip", kwargs={"pk": self.client_obj.pk}))
        self.assertEqual(response.status_code, 403)

    def test_readonly_with_can_send_mass_email_still_cannot_send_mass_email(self):
        perms = self.read_only.employee_permission
        perms.can_send_mass_email = True
        perms.save(update_fields=["can_send_mass_email", "updated_at"])

        self.client.force_login(self.read_only)
        response = self.client.post(reverse("clients:mass_email"), data={"subject": "x", "message": "y"})
        self.assertEqual(response.status_code, 403)

    def test_readonly_with_can_view_reports_can_access_metrics(self):
        perms = self.read_only.employee_permission
        perms.can_view_reports = True
        perms.save(update_fields=["can_view_reports", "updated_at"])

        self.client.force_login(self.read_only)
        response = self.client.get(reverse("clients:metrics_dashboard"))
        self.assertEqual(response.status_code, 200)
