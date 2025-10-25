from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from .models import Client


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


class ClientPrintingViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username='staff', password='pass', is_staff=True
        )

        self.client_record = Client.objects.create(
            first_name='Jan',
            last_name='Kowalski',
            case_number='AB/12345',
            submission_date=datetime(2024, 1, 15).date(),
            email='jan@example.com',
            phone='+48123123123',
            citizenship='PL',
        )

    def test_wsc_print_view_renders_client_details(self):
        login_successful = self.client.login(username='staff', password='pass')
        self.assertTrue(login_successful)

        with translation.override('pl'):
            url = reverse('clients:client_print_wsc', kwargs={'pk': self.client_record.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('value="Warszawa, 15.01.2024"', html)
        self.assertIn('name="wsc_sygnatura"', html)
        self.assertIn('value="AB/12345"', html)
        self.assertIn('value="Jan Kowalski"', html)
        self.assertIn('value="15.01.2024"', html)
        self.assertIn('value="PL"', html)
        self.assertIn('value="+48123123123"', html)
        self.assertIn('value="jan@example.com"', html)

    def test_wsc_print_view_leaves_missing_fields_blank(self):
        login_successful = self.client.login(username='staff', password='pass')
        self.assertTrue(login_successful)

        empty_client = Client.objects.create(
            first_name='',
            last_name='',
            citizenship='PL',
            phone='',
            email='empty@example.com',
        )

        with translation.override('pl'):
            url = reverse('clients:client_print_wsc', kwargs={'pk': empty_client.pk})

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Ensure no placeholder text is injected for missing optional fields.
        html = response.content.decode()
        self.assertNotIn('None', html)
        self.assertIn('name="wsc_sygnatura"', html)
        self.assertIn('value=""', html)
