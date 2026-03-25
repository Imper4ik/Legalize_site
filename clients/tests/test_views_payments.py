import json
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.contrib.auth import get_user_model

from clients.models import Client, Payment

User = get_user_model()


class PaymentViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        self.client_obj = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            email="ivan@example.com",
            phone="123456789",
            application_purpose='work',
        )
        self.client = DjangoClient()
        self.client.login(email="staff@example.com", password="password123")
        
        self.payment = Payment.objects.create(
            client=self.client_obj,
            service_description='study_service',
            total_amount=500.00,
            amount_paid=500.00,
            payment_method='cash',
            status='paid',
        )

    def test_add_payment_standard(self):
        url = reverse('clients:add_payment', kwargs={'client_id': self.client_obj.id})
        data = {
            'service_description': 'work_service',
            'total_amount': '1500.00',
            'amount_paid': '0.00',
            'payment_method': 'card',
            'status': 'pending',
        }
        response = self.client.post(url, data=data)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.assertTrue(Payment.objects.filter(client=self.client_obj, service_description='work_service', total_amount=1500.00).exists())

    def test_add_payment_json(self):
        url = reverse('clients:add_payment', kwargs={'client_id': self.client_obj.id})
        data = {
            'service_description': 'work_service',
            'total_amount': '800.00',
            'amount_paid': '800.00',
            'payment_method': 'transfer',
            'status': 'paid',
        }
        response = self.client.post(url, data=data, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')
        self.assertTrue(Payment.objects.filter(total_amount=800.00).exists())

    def test_add_payment_invalid_json(self):
        url = reverse('clients:add_payment', kwargs={'client_id': self.client_obj.id})
        data = {
            'service_description': '',  # invalid
        }
        # This will fail at form level if service_description is required
        response = self.client.post(url, data=data, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        # ResponseHelper.error returns 400 by default
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get('status'), 'error')
        self.assertIn('errors', response.json())

    def test_edit_payment_standard(self):
        url = reverse('clients:edit_payment', kwargs={'payment_id': self.payment.id})
        data = {
            'service_description': 'study_service',
            'total_amount': '600.00',
            'amount_paid': '300.00',
            'payment_method': 'card',
            'status': 'partial',
        }
        response = self.client.post(url, data=data)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.total_amount, 600.00)

    def test_edit_payment_json(self):
        url = reverse('clients:edit_payment', kwargs={'payment_id': self.payment.id})
        data = {
            'service_description': 'study_service',
            'total_amount': '700.00',
            'amount_paid': '700.00',
            'payment_method': 'card',
            'status': 'paid',
        }
        response = self.client.post(url, data=data, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.total_amount, 700.00)

    def test_delete_payment_standard(self):
        url = reverse('clients:delete_payment', kwargs={'payment_id': self.payment.id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.assertFalse(Payment.objects.filter(id=self.payment.id).exists())

    def test_delete_payment_json(self):
        url = reverse('clients:delete_payment', kwargs={'payment_id': self.payment.id})
        response = self.client.post(url, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')
        self.assertFalse(Payment.objects.filter(id=self.payment.id).exists())

    def test_get_price_for_service(self):
        url = reverse('clients:get_price_for_service', kwargs={'service_value': 'study_service'})
        response = self.client.get(url, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('price', data)
