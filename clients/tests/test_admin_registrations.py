from __future__ import annotations

from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from clients.models import Client, DocumentProcessingJob, EmailCampaign, EmailLog, MOSApplicationData, Reminder


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
