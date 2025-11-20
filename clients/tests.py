import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import translation

from allauth.account.models import EmailAddress

from .models import Client, Document
from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.services.responses import NO_STORE_HEADER, ResponseHelper


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
        self.assertIsNotNone(results)
        self.assertEqual(results.monthly_tuition_calculated, Decimal('1000.00'))
        self.assertEqual(results.tuition_total, Decimal('6000.00'))


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
        self.assertContains(response, 'Jan')
        self.assertContains(response, 'Kowalski')
        self.assertContains(response, 'AB/12345')
        self.assertContains(response, '15.01.2024')

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
        self.assertNotIn('None', response.content.decode())


class ClientAccountLifecycleTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_deleting_client_removes_linked_user_account(self):
        user = self.user_model.objects.create_user(
            username='client-user', email='client@example.com', password='secret123'
        )
        EmailAddress.objects.create(
            user=user,
            email='client@example.com',
            primary=True,
            verified=True,
        )

        client = Client.objects.create(
            first_name='Client',
            last_name='User',
            citizenship='PL',
            phone='+48111222333',
            email='client@example.com',
            user=user,
        )

        client.delete()

        self.assertFalse(self.user_model.objects.filter(pk=user.pk).exists())
        self.assertFalse(EmailAddress.objects.filter(email='client@example.com').exists())

    def test_staff_accounts_are_preserved_when_client_deleted(self):
        staff_user = self.user_model.objects.create_user(
            username='staff-owned',
            email='staff-owned@example.com',
            password='secret123',
            is_staff=True,
        )

        client = Client.objects.create(
            first_name='Support',
            last_name='Owner',
            citizenship='PL',
            phone='+48123456789',
            email='staff-owned@example.com',
            user=staff_user,
        )

        client.delete()

        self.assertTrue(self.user_model.objects.filter(pk=staff_user.pk).exists())



class DocumentTypeConsistencyTests(TestCase):
    def test_document_model_choices_follow_enum(self):
        self.assertEqual(list(Document.DOC_TYPES), list(DocumentType.choices))

    def test_document_checklist_labels_match_enum(self):
        enum_map = {choice.value: choice.label for choice in DocumentType}
        for docs in DOCUMENT_CHECKLIST.values():
            for code, label in docs:
                self.assertIn(code, enum_map)
                self.assertEqual(label, enum_map[code])


class ResponseHelperTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_expects_json_true_for_ajax_header(self):
        request = self.factory.get('/path', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        helper = ResponseHelper(request)
        self.assertTrue(helper.expects_json)

    def test_success_response_contains_no_store_header(self):
        request = self.factory.post('/path')
        helper = ResponseHelper(request)

        response = helper.success(message='ok', extra='yes')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], NO_STORE_HEADER)
        self.assertJSONEqual(response.content, {'status': 'success', 'message': 'ok', 'extra': 'yes'})

    def test_error_response_includes_errors_and_status(self):
        request = self.factory.post('/path')
        helper = ResponseHelper(request)

        response = helper.error(message='bad', status=422, errors={'field': ['error']})

        self.assertEqual(response.status_code, 422)
        self.assertJSONEqual(
            response.content,
            {'status': 'error', 'message': 'bad', 'errors': {'field': ['error']}}
        )

    def test_forbidden_response_has_error_status(self):
        request = self.factory.get('/path', HTTP_ACCEPT='application/json')
        helper = ResponseHelper(request)

        response = helper.forbidden()

        self.assertEqual(response.status_code, 403)
        content = json.loads(response.content)
        self.assertEqual(content['status'], 'error')
        self.assertIn('message', content)
