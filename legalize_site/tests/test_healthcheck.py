from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
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
