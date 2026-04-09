from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, Document, Payment
from clients.services.responses import NO_STORE_HEADER, ResponseHelper, apply_no_store
from clients.constants import DocumentType


class ResponseHelpersStage8Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_apply_no_store_sets_cache_control_header(self):
        response = HttpResponse("ok")

        updated = apply_no_store(response)

        self.assertEqual(updated["Cache-Control"], NO_STORE_HEADER)

    def test_response_helper_success_payload_and_no_store(self):
        request = self.factory.get("/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        helper = ResponseHelper(request)

        response = helper.success(message="done", value=1)
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["message"], "done")
        self.assertEqual(payload["value"], 1)
        self.assertEqual(response["Cache-Control"], NO_STORE_HEADER)

    def test_response_helper_error_payload(self):
        request = self.factory.get("/", HTTP_ACCEPT="application/json")
        helper = ResponseHelper(request)

        response = helper.error(message="bad", status=422, errors={"field": ["required"]})
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 422)
        self.assertEqual(payload["status"], "error")
        self.assertIn("errors", payload)

    def test_response_helper_forbidden(self):
        request = self.factory.get("/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        helper = ResponseHelper(request)

        response = helper.forbidden()
        payload = json.loads(response.content.decode("utf-8"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["status"], "error")


class MetricsDashboardStage8Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(email="metrics_staff@example.com", password="pass", is_staff=True)
        self.client.login(email="metrics_staff@example.com", password="pass")

        today = timezone.localdate()

        # Client with docs + paid + closed
        c1 = Client.objects.create(
            first_name="A",
            last_name="One",
            citizenship="PL",
            phone="+48111111111",
            email="a1@example.com",
            decision_date=today,
        )
        Document.objects.create(
            client=c1,
            document_type=DocumentType.PASSPORT.value,
            file="documents/pass1.pdf",
            expiry_date=today + timedelta(days=5),
        )
        Payment.objects.create(
            client=c1,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="100.00",
            status="paid",
        )

        # Client with payment but no paid status
        c2 = Client.objects.create(
            first_name="B",
            last_name="Two",
            citizenship="PL",
            phone="+48222222222",
            email="b2@example.com",
        )
        Payment.objects.create(
            client=c2,
            service_description="consultation",
            total_amount="100.00",
            amount_paid="0.00",
            status="pending",
        )

    def test_metrics_dashboard_renders_funnel_context(self):
        response = self.client.get(reverse("clients:metrics_dashboard"))

        self.assertEqual(response.status_code, 200)
        funnel = response.context["funnel"]
        self.assertGreaterEqual(funnel["clients_created"], 2)
        self.assertGreaterEqual(funnel["clients_with_docs"], 1)
        self.assertGreaterEqual(funnel["clients_with_payments"], 2)
        self.assertGreaterEqual(funnel["clients_paid"], 1)
        self.assertGreaterEqual(funnel["cases_closed"], 1)
        self.assertIn("overdue_sla", response.context)
