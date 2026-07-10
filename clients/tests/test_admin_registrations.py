from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase

from clients.models import (
    Client,
    DocumentProcessingJob,
    EmailCampaign,
    EmailLog,
    MOSApplicationData,
    Reminder,
    StaffAuditEvent,
)


class AdminRegistrationTests(SimpleTestCase):
    def test_operational_models_are_visible_in_django_admin(self):
        for model in (Reminder, EmailLog, DocumentProcessingJob, EmailCampaign):
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)

    def test_masked_mos_admin_fields_are_not_duplicated(self):
        request = RequestFactory().get("/admin/")
        request.user = type("NoSensitiveUser", (), {"has_perm": lambda self, perm: False})()

        for model in (Client, MOSApplicationData):
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry[model]
                if model is Client:
                    from django.contrib.admin.utils import flatten_fieldsets

                    fields = flatten_fieldsets(model_admin.get_fieldsets(request))
                else:
                    fields = model_admin.get_fields(request)
                self.assertEqual(len(fields), len(set(fields)))


class StaffAuditEventAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(email="audit-admin@example.com", password="pass")
        self.actor = user_model.objects.create_user(email="audit-actor@example.com", password="pass", is_staff=True)
        self.target = user_model.objects.create_user(email="audit-target@example.com", password="pass", is_staff=True)

    def test_staff_audit_admin_is_view_only(self):
        request = RequestFactory().get("/admin/")
        request.user = self.admin_user
        model_admin = admin.site._registry[StaffAuditEvent]

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertIn("target_display", model_admin.list_display)
        self.assertIn("actor_display", model_admin.list_display)

    def test_staff_audit_display_prefers_snapshot_labels(self):
        event = StaffAuditEvent.objects.create(
            actor=self.actor,
            target=self.target,
            actor_label="Original Actor",
            target_label="Original Target",
            event_type=StaffAuditEvent.EVENT_STAFF_UPDATED,
            summary="Staff updated",
            metadata={},
        )

        self.actor.email = "changed-actor@example.com"
        self.actor.save(update_fields=["email"])
        self.target.delete()
        event.refresh_from_db()

        self.assertIsNone(event.target_id)
        self.assertEqual(event.actor_display, "Original Actor")
        self.assertEqual(event.target_display, "Original Target")
