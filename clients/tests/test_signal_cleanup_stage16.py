from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from clients.models import Client, Payment, Reminder


class SignalCleanupStage16Tests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.portal_user = user_model.objects.create_user(
            email="client-portal@example.com",
            password="pass",
            is_staff=False,
            is_active=True,
        )
        self.client_obj = Client.objects.create(
            first_name="Oksana",
            last_name="Duda",
            citizenship="UA",
            phone="+48555555555",
            email="oksana-stage16@example.com",
            user=self.portal_user,
        )

    def test_archiving_payment_deactivates_linked_reminder(self):
        payment = Payment.objects.create(
            client=self.client_obj,
            service_description="consultation",
            total_amount=Decimal("100.00"),
            amount_paid=Decimal("20.00"),
            status="partial",
            due_date=timezone.localdate(),
        )
        reminder = Reminder.objects.get(payment=payment)

        payment.archive()

        reminder.refresh_from_db()
        self.assertFalse(reminder.is_active)

    def test_archiving_client_deactivates_non_staff_user(self):
        self.client_obj.archive()

        self.portal_user.refresh_from_db()
        self.assertFalse(self.portal_user.is_active)
