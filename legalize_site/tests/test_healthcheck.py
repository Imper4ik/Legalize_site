from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clients.models import Client, Document, DocumentProcessingJob, EmailCampaign


class HealthcheckViewTests(TestCase):
    def test_healthcheck_returns_minimal_payload_by_default(self):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json().keys()), {"status", "database"})

    def test_staff_healthcheck_details_include_queues_and_runtime(self):
        user_model = get_user_model()
        staff = user_model.objects.create_user(email="ops@example.com", password="pass", is_staff=True)
        self.client.force_login(staff)
        client = Client.objects.create(
            first_name="Ops",
            last_name="Case",
            citizenship="PL",
            phone="+48100100100",
            email="ops-case@example.com",
        )
        document = Document.objects.create(
            client=client,
            document_type="passport",
            file="documents/ops.pdf",
        )

        EmailCampaign.objects.create(
            subject="Queued",
            message="Body",
            total_recipients=1,
            recipient_emails=["queued@example.com"],
        )
        EmailCampaign.objects.create(
            subject="Running",
            message="Body",
            total_recipients=1,
            recipient_emails=["running@example.com"],
            status=EmailCampaign.STATUS_RUNNING,
        )
        DocumentProcessingJob.objects.create(
            document=document,
        )

        response = self.client.get(reverse("healthcheck"), {"details": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("queues", payload)
        self.assertIn("runtime", payload)
        self.assertEqual(payload["queues"]["pending_document_jobs"], 1)
        self.assertEqual(payload["queues"]["pending_email_campaigns"], 1)
        self.assertEqual(payload["queues"]["running_email_campaigns"], 1)

    def test_readiness_returns_minimal_public_payload(self):
        response = self.client.get(reverse("readiness"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload, {"status": "ok"})

    def test_staff_readiness_details_include_component_statuses(self):
        user_model = get_user_model()
        staff = user_model.objects.create_user(email="ready@example.com", password="pass", is_staff=True)
        self.client.force_login(staff)

        response = self.client.get(reverse("readiness"), {"details": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("database", payload["components"])
        self.assertIn("cache", payload["components"])
        self.assertIn("runtime", payload["components"])
        self.assertEqual(payload["components"]["database"]["status"], "ok")

    @override_settings(IS_PRODUCTION=True)
    @patch("legalize_site.views.cache.set", side_effect=RuntimeError("cache unavailable"))
    def test_production_readiness_fails_when_cache_is_unavailable(self, _cache_set_mock):
        response = self.client.get(reverse("readiness"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "degraded"})
