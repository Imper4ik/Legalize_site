import json
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import translation

from allauth.account.models import EmailAddress

from .forms import DocumentChecklistForm
from .models import Client, Document, DocumentRequirement
from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.services.notifications import send_missing_documents_email
from clients.services.responses import NO_STORE_HEADER, ResponseHelper
from clients.services.wezwanie_parser import parse_wezwanie


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
    def test_document_checklist_labels_match_enum(self):
        enum_map = {choice.value: choice.label for choice in DocumentType}
        for docs in DOCUMENT_CHECKLIST.values():
            for code, label in docs:
                self.assertIn(code, enum_map)
                self.assertEqual(label, enum_map[code])

    def test_document_display_name_prefers_custom_label(self):
        client = Client.objects.create(
            first_name='Jan',
            last_name='Kowalski',
            citizenship='PL',
            phone='+48123123123',
            email='jan@example.com',
            application_purpose='work',
        )
        DocumentRequirement.objects.create(
            application_purpose='work', document_type='zus_rca', custom_name='ZUS RCA'
        )
        doc = Document.objects.create(
            client=client,
            document_type='zus_rca',
            file=SimpleUploadedFile('test.pdf', b'filecontent'),
        )

        self.assertEqual(doc.display_name, 'ZUS RCA')
class DocumentRequirementTests(TestCase):
    def test_required_for_respects_database_overrides(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PASSPORT, position=1
        )
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PHOTOS, position=0
        )

        self.assertEqual(
            DocumentRequirement.required_for('work'),
            [
                (DocumentType.PHOTOS.value, DocumentType.PHOTOS.label),
                (DocumentType.PASSPORT.value, DocumentType.PASSPORT.label),
            ],
        )

    def test_client_checklist_falls_back_when_no_records(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        client = Client.objects.create(
            first_name='Anna',
            last_name='Nowak',
            citizenship='PL',
            phone='+48123123123',
            email='anna@example.com',
            application_purpose='work',
            language='pl',
        )

        checklist = client.get_document_checklist()
        fallback = DOCUMENT_CHECKLIST.get(('work', 'pl'))
        self.assertEqual(len(checklist), len(fallback))

    def test_client_checklist_respects_disabled_custom_items(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        DocumentRequirement.objects.create(
            application_purpose='work',
            document_type=DocumentType.PASSPORT,
            is_required=False,
            position=0,
        )

        client = Client.objects.create(
            first_name='Anna',
            last_name='Nowak',
            citizenship='PL',
            phone='+48123123123',
            email='anna-disabled@example.com',
            application_purpose='work',
            language='pl',
        )

        checklist = client.get_document_checklist()
        self.assertEqual(checklist, [])

    def test_add_form_allows_custom_document(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        form = DocumentRequirementAddForm(data={'name': 'Дополнительная справка'}, purpose='work')

        self.assertTrue(form.is_valid())
        requirement = form.save()

        self.assertEqual(requirement.document_type, 'дополнительная_справка')
        self.assertEqual(requirement.custom_name, 'Дополнительная справка')
        self.assertTrue(requirement.is_required)

    def test_add_form_generates_unique_slug_when_exists(self):
        DocumentRequirement.objects.filter(application_purpose='study').delete()
        DocumentRequirement.objects.create(
            application_purpose='study', document_type='custom_doc', custom_name='Test', position=0
        )

        form = DocumentRequirementAddForm(data={'name': 'Custom doc'}, purpose='study')
        self.assertTrue(form.is_valid())
        saved = form.save()

        self.assertNotEqual(saved.document_type, 'custom_doc')
        self.assertTrue(saved.document_type.startswith('custom_doc'))

    def test_edit_form_updates_required_flag(self):
        DocumentRequirement.objects.filter(application_purpose='work', document_type=DocumentType.PASSPORT).delete()
        requirement = DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PASSPORT, custom_name='Паспорт', position=0
        )

        form = DocumentRequirementEditForm(
            data={'custom_name': 'Паспорт клиента', 'is_required': False},
            instance=requirement,
        )

        self.assertTrue(form.is_valid())
        updated = form.save()

        self.assertFalse(updated.is_required)
        self.assertEqual(updated.custom_name, 'Паспорт клиента')


class DocumentRequirementTests(TestCase):
    def test_required_for_respects_database_overrides(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PASSPORT, position=1
        )
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PHOTOS, position=0
        )

        self.assertEqual(
            DocumentRequirement.required_for('work'),
            [
                (DocumentType.PHOTOS.value, DocumentType.PHOTOS.label),
                (DocumentType.PASSPORT.value, DocumentType.PASSPORT.label),
            ],
        )

    def test_client_checklist_falls_back_when_no_records(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        client = Client.objects.create(
            first_name='Anna',
            last_name='Nowak',
            citizenship='PL',
            phone='+48123123123',
            email='anna@example.com',
            application_purpose='work',
            language='pl',
        )

        checklist = client.get_document_checklist()
        fallback = DOCUMENT_CHECKLIST.get(('work', 'pl'))
        self.assertEqual(len(checklist), len(fallback))

    def test_checklist_form_saves_selected_documents(self):
        DocumentRequirement.objects.filter(application_purpose='study').delete()
        form = DocumentChecklistForm(
            data={'required_documents': [DocumentType.PASSPORT, DocumentType.PAYMENT_CONFIRMATION]},
            purpose='study',
        )
        self.assertTrue(form.is_valid())
        saved_count = form.save()

        self.assertEqual(saved_count, 2)
        self.assertEqual(
            DocumentRequirement.required_for('study'),
            [
                (DocumentType.PASSPORT.value, DocumentType.PASSPORT.label),
                (DocumentType.PAYMENT_CONFIRMATION.value, DocumentType.PAYMENT_CONFIRMATION.label),
            ],
        )

    def test_checklist_form_keeps_all_unchecked_when_custom_exists(self):
        DocumentRequirement.objects.filter(application_purpose='study').delete()
        DocumentRequirement.objects.create(
            application_purpose='study',
            document_type=DocumentType.PASSPORT,
            is_required=False,
            position=0,
        )

        form = DocumentChecklistForm(data=None, purpose='study')

        self.assertEqual(form.initial['required_documents'], [])


class WezwanieParserTests(TestCase):
    def test_parses_case_number_and_date_from_text(self):
        content = "Wezwanie\nNumer sprawy: ABC/123/24\nw dniu 12.05.2024 pobrano odciski"
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as temp:
            temp.write(content)
            temp_path = temp.name

        parsed = parse_wezwanie(temp_path)

        self.assertEqual(parsed.case_number, "ABC/123/24")
        self.assertEqual(parsed.fingerprints_date, date(2024, 5, 12))

        Path(temp_path).unlink(missing_ok=True)

    def test_normalizes_case_number_with_spaces_and_noise(self):
        content = (
            "Numer sprawy:  40 93 66 ;\\n"
            "w dniu 12.05.2024 pobrano odciski"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as temp:
            temp.write(content)
            temp_path = temp.name

        parsed = parse_wezwanie(temp_path)

        self.assertEqual(parsed.case_number, "409366")
        self.assertEqual(parsed.fingerprints_date, date(2024, 5, 12))

        Path(temp_path).unlink(missing_ok=True)


class MissingDocumentsEmailTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            first_name="Anna",
            last_name="Nowak",
            citizenship="PL",
            phone="+48123123123",
            email="anna@example.com",
            application_purpose="work",
            language="pl",
        )

        mail.outbox = []

        DocumentRequirement.objects.filter(application_purpose="work").delete()
        DocumentRequirement.objects.create(
            application_purpose="work", document_type=DocumentType.PASSPORT, position=0
        )

    def test_sends_email_when_documents_missing(self):
        sent = send_missing_documents_email(self.client_record)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Паспорт", mail.outbox[0].body)

    def test_skips_email_when_nothing_missing(self):
        Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.PASSPORT,
            file=SimpleUploadedFile("passport.pdf", b"content"),
        )

        sent = send_missing_documents_email(self.client_record)
        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)


class WezwanieUploadFlowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username="staff_wezwanie", password="pass", is_staff=True
        )

        DocumentRequirement.objects.filter(application_purpose="work").delete()
        DocumentRequirement.objects.create(
            application_purpose="work", document_type=DocumentType.PASSPORT, position=0
        )
        DocumentRequirement.objects.create(
            application_purpose="work", document_type=DocumentType.PHOTOS, position=1
        )

        self.client_record = Client.objects.create(
            first_name="Jan",
            last_name="Test",
            citizenship="PL",
            phone="+48123123123",
            email="wezwanie@example.com",
            application_purpose="work",
            language="pl",
        )

        mail.outbox = []

    def test_uploading_wezwanie_updates_fields_and_sends_missing_docs_email(self):
        login_successful = self.client.login(username="staff_wezwanie", password="pass")
        self.assertTrue(login_successful)

        content = b"Numer sprawy: ZZ/987/24\nw dniu 05-06-2024 pobrano odciski"
        upload = SimpleUploadedFile("wezwanie.txt", content)
        url = reverse(
            "clients:add_document",
            kwargs={"client_id": self.client_record.pk, "doc_type": "wezwanie"},
        )

        response = self.client.post(url, {"file": upload}, follow=True)

        self.assertEqual(response.status_code, 200)

        updated_client = Client.objects.get(pk=self.client_record.pk)
        self.assertEqual(updated_client.case_number, "ZZ/987/24")
        self.assertEqual(updated_client.fingerprints_date, date(2024, 6, 5))

        self.assertTrue(
            Document.objects.filter(client=updated_client, document_type="wezwanie").exists()
        )

        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn("Паспорт", mail.outbox[0].body)
        self.assertIn("Фотографии", mail.outbox[0].body)


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
