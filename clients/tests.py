from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from clients.models import Client


class CalculatorViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username='staff', password='pass', is_staff=True
        )

    def test_months_in_period_multiplies_tuition_total(self):
        login_successful = self.client.login(username='staff', password='pass')
        self.assertTrue(login_successful)

        future_date = (datetime.now() + timedelta(days=30)).strftime('%d-%m-%Y')
        with translation.override('ru'):
            url = reverse('clients:calculator')

        response = self.client.post(url, {
            'total_end_date': future_date,
            'tuition_fee': '1000',
            'tuition_currency': 'PLN',
            'months_in_period': '6',
            'rent_and_bills': '0',
            'rent_currency': 'PLN',
            'num_people': '1',
            'fee_type': 'per_month',
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.context)
        results = response.context['results']
        self.assertEqual(results['monthly_tuition_calculated'], '1 000.00')
        self.assertEqual(results['tuition_total'], '6 000.00')


class ClientCreateViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username='creator', password='pass', is_staff=True
        )

    def test_successful_client_creation_redirects_with_feedback(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('clients:client_add'),
            {
                'first_name': 'Anna',
                'last_name': 'Nowak',
                'email': 'anna@example.com',
                'phone': '+48 600 000 000',
                'citizenship': 'Poland',
                'passport_num': '',
                'case_number': '',
                'application_purpose': 'study',
                'language': 'pl',
                'status': 'new',
                'basis_of_stay': '',
                'legal_basis_end_date': '',
                'submission_date': '',
                'employer_phone': '',
                'fingerprints_date': '',
                'notes': '',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('clients:client_list'))
        self.assertTrue(Client.objects.filter(email='anna@example.com').exists())
        messages = list(response.context['messages'])
        self.assertTrue(any('успешно' in message.message.lower() for message in messages))

    def test_invalid_client_creation_shows_errors(self):
        self.client.force_login(self.staff_user)

        response = self.client.post(
            reverse('clients:client_add'),
            {
                'first_name': '',
                'last_name': '',
                'email': 'not-an-email',
                'phone': '',
                'citizenship': '',
            },
        )

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertTrue(form.errors)
        self.assertIn('first_name', form.errors)
        self.assertIn('email', form.errors)
        flash_messages = list(response.context['messages'])
        self.assertTrue(any('не удалось сохранить' in message.message.lower() for message in flash_messages))
        self.assertEqual(Client.objects.count(), 0)
