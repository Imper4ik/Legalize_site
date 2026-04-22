from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from clients.constants import DocumentType
from clients.models import Client, ClientActivity, Document, Payment


class RestoreFlowStage17Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.manager = user_model.objects.create_user(
            email="manager-stage17@example.com",
            password="pass",
            is_staff=True,
        )
        managers = Group.objects.get_or_create(name="Manager")[0]
        self.manager.groups.add(managers)
        self.client.force_login(self.manager)

        self.client_obj = Client.objects.create(
            first_name="Yuliia",
            last_name="Storozhuk",
            citizenship="UA",
            phone="+48666666666",
            email="yuliia-stage17@example.com",
            assigned_staff=self.manager,
        )

    def test_manager_can_restore_archived_client(self):
        self.client_obj.archive()

        response = self.client.post(reverse("clients:client_restore", kwargs={"pk": self.client_obj.pk}))

        self.assertEqual(response.status_code, 302)
        self.client_obj.refresh_from_db()
        self.assertIsNone(self.client_obj.archived_at)
        self.assertTrue(
            ClientActivity.objects.filter(
                client=self.client_obj,
                event_type="client_updated",
                metadata__restored_object="client",
            ).exists()
        )

    def test_manager_can_restore_archived_document(self):
        document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT.value,
            file="documents/test.pdf",
        )
        document.archive()

        response = self.client.post(reverse("clients:document_restore", kwargs={"pk": document.pk}))

        self.assertEqual(response.status_code, 302)
        document.refresh_from_db()
        self.assertIsNone(document.archived_at)

    def test_manager_can_restore_archived_payment(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("0.00"),
            status="pending",
        )
        payment.archive()

        response = self.client.post(reverse("clients:payment_restore", kwargs={"pk": payment.pk}))

        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.assertIsNone(payment.archived_at)
