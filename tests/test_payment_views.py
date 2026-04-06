"""Tests for payment views: add, edit, delete, get_price_for_service."""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

from clients.models import Client, Payment

User = get_user_model()


class PaymentViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")
        self.test_client = Client.objects.create(
            first_name="Jan", last_name="Kowalski", citizenship="Poland",
            phone="123456789", email="jan_pay@test.com", application_purpose="work",
        )

    def test_add_payment_post(self):
        url = reverse("clients:add_payment", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url, {
            "service_description": "work_service",
            "total_amount": "1800.00",
            "amount_paid": "0.00",
            "status": "pending",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Payment.objects.filter(client=self.test_client).count(), 1)

    def test_add_payment_ajax(self):
        url = reverse("clients:add_payment", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url, {
            "service_description": "work_service",
            "total_amount": "1800.00",
            "amount_paid": "0.00",
            "status": "pending",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")

    def test_edit_payment(self):
        payment = Payment.objects.create(
            client=self.test_client, service_description="work_service",
            total_amount=1800, amount_paid=0, status="pending",
        )
        url = reverse("clients:edit_payment", kwargs={"payment_id": payment.pk})
        resp = self.client.post(url, {
            "service_description": "study_service",
            "total_amount": "1400.00",
            "amount_paid": "1400.00",
            "status": "paid",
        })
        self.assertEqual(resp.status_code, 302)
        payment.refresh_from_db()
        self.assertEqual(payment.status, "paid")

    def test_delete_payment(self):
        payment = Payment.objects.create(
            client=self.test_client, service_description="work_service",
            total_amount=1800, amount_paid=0, status="pending",
        )
        url = reverse("clients:delete_payment", kwargs={"payment_id": payment.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())

    def test_get_price_for_service_api(self):
        url = reverse("clients:get_price_for_service", kwargs={"service_value": "work_service"})
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("price", data)

    def test_add_payment_invalid_form(self):
        url = reverse("clients:add_payment", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url, {
            "service_description": "",
            "total_amount": "",
        }, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["status"], "error")
