from __future__ import annotations

from django.contrib import admin
from django.test import SimpleTestCase

from clients.models import DocumentProcessingJob, EmailCampaign, EmailLog, Reminder


class AdminRegistrationTests(SimpleTestCase):
    def test_operational_models_are_visible_in_django_admin(self):
        for model in (Reminder, EmailLog, DocumentProcessingJob, EmailCampaign):
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)
