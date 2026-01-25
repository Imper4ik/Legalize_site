import json
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from gettext import GNUTranslations
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import translation

import shutil

from allauth.account.models import EmailAddress

from .forms import DocumentChecklistForm
from .models import Client, Document, DocumentRequirement, translate_document_name
from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.services.notifications import send_expiring_documents_email, send_missing_documents_email
from clients.services.responses import NO_STORE_HEADER, ResponseHelper
from clients.services.wezwanie_parser import parse_wezwanie


class PurePythonMsgfmtTests(SimpleTestCase):
    def test_compiled_mo_file_is_valid_utf8(self):
        from legalize_site.utils.i18n import _write_mo_file

        with tempfile.TemporaryDirectory() as tmp:
            locale_dir = Path(tmp) / "ru" / "LC_MESSAGES"
            locale_dir.mkdir(parents=True)
            po_path = locale_dir / "django.po"
            po_path.write_text(
                '\n'.join(
                    [
                        'msgid ""',
                        'msgstr ""',
                        '"Content-Type: text/plain; charset=UTF-8\\n"',
                        '"Language: ru\\n"',
                        '',
                        'msgid "hello"',
                        'msgstr "привет"',
                    ]
                ),
                encoding="utf-8",
            )

            mo_path = po_path.with_suffix(".mo")
            _write_mo_file(po_path, mo_path)

            with mo_path.open("rb") as fp:
                translations = GNUTranslations(fp)

            self.assertEqual(translations.gettext("hello"), "привет")
            self.assertEqual(translations.gettext("missing"), "missing")


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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._can_compile_messages = shutil.which("msgfmt") is not None
        if cls._can_compile_messages:
            call_command("compilemessages", verbosity=0, ignore=["venv", ".venv"])

    def test_document_checklist_labels_match_enum(self):
        enum_map = {choice.value: choice.label for choice in DocumentType}
        for docs in DOCUMENT_CHECKLIST.values():
            for code, label in docs:
                self.assertIn(code, enum_map)
                self.assertEqual(label, enum_map[code])

    def test_translate_document_name_respects_language(self):
        if not self._can_compile_messages:
            self.skipTest("msgfmt is not available to compile translations")

        with translation.override("ru"):
            self.assertEqual(
                translate_document_name(DocumentType.PHOTOS.label),
                "Фотографии (4 шт., 45x35 мм)",
            )

        with translation.override("en"):
            self.assertEqual(
                translate_document_name(DocumentType.PHOTOS.label),
                "4 photos (45x35 mm)",
            )

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

    def test_required_for_uses_default_label_when_custom_matches_translation(self):
        if not self._can_compile_messages:
            self.skipTest("msgfmt is not available to compile translations")

        DocumentRequirement.objects.filter(application_purpose='work').delete()
        with translation.override("ru"):
            ru_label = str(DocumentType.PASSPORT.label)

        DocumentRequirement.objects.create(
            application_purpose='work',
            document_type=DocumentType.PASSPORT,
            custom_name=ru_label,
            position=0,
        )

        required = DocumentRequirement.required_for('work')
        self.assertIn((DocumentType.PASSPORT.value, DocumentType.PASSPORT.label), required)


class DocumentRequirementFormTests(TestCase):
    def test_required_for_respects_database_overrides(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PASSPORT, position=1
        )
        DocumentRequirement.objects.create(
            application_purpose='work', document_type=DocumentType.PHOTOS, position=0
        )

        required = DocumentRequirement.required_for('work')
        self.assertGreaterEqual(len(required), 2)
        self.assertEqual(required[0], (DocumentType.PHOTOS.value, DocumentType.PHOTOS.label))
        self.assertEqual(required[1], (DocumentType.PASSPORT.value, DocumentType.PASSPORT.label))

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
        codes = [item["code"] for item in checklist]
        self.assertNotIn(DocumentType.PASSPORT.value, codes)
        self.assertGreater(len(checklist), 0)

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


class DocumentChecklistFormTests(TestCase):
    def test_checklist_form_saves_selected_documents(self):
        DocumentRequirement.objects.filter(application_purpose='study').delete()
        form = DocumentChecklistForm(
            data={'required_documents': [DocumentType.PASSPORT, DocumentType.ENROLLMENT_CERTIFICATE]},
            purpose='study',
        )
        self.assertTrue(form.is_valid())
        saved_count = form.save()

        self.assertEqual(saved_count, 2)
        required = DocumentRequirement.required_for('study')
        self.assertIn((DocumentType.PASSPORT.value, DocumentType.PASSPORT.label), required)
        self.assertIn(
            (
                DocumentType.ENROLLMENT_CERTIFICATE.value,
                DocumentType.ENROLLMENT_CERTIFICATE.label,
            ),
            required,
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

    def test_checklist_form_limits_choices_to_purpose(self):
        DocumentRequirement.objects.filter(application_purpose='work').delete()

        form = DocumentChecklistForm(data=None, purpose='work')

        choice_keys = [value for value, _ in form.fields['required_documents'].choices]

        self.assertIn(DocumentType.WORK_PERMIT_FEE, choice_keys)
        self.assertNotIn(DocumentType.TUITION_FEE_PROOF, choice_keys)


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

    def test_parses_full_name_with_pan_pani_label(self):
        content = (
            "WEZWANIE\n"
            "Pan/Pani Maria KOWALSKA\n"
            "Sygnatura akt: WSC-II-S.6151.97770.2023\n"
            "w dniu 01.04.2024 pobrano odciski"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as temp:
            temp.write(content)
            temp_path = temp.name

        parsed = parse_wezwanie(temp_path)

        self.assertEqual(parsed.full_name, "Maria KOWALSKA")
        self.assertEqual(parsed.case_number, "WSC-II-S.6151.97770.2023")

        Path(temp_path).unlink(missing_ok=True)

    def test_parses_case_number_with_sprawa_nr_keyword(self):
        content = (
            "Sprawa nr: II SA/Wa 1234/24\n"
            "Pani Anna Nowak\n"
            "w dniu 03-06-2024 pobrano odciski"
        )
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as temp:
            temp.write(content)
            temp_path = temp.name

        parsed = parse_wezwanie(temp_path)

        self.assertEqual(parsed.case_number, "IISA/WA1234/24")
        self.assertEqual(parsed.full_name, "Anna Nowak")

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

        with translation.override(self.client_record.language):
            self.passport_label = translate_document_name(DocumentType.PASSPORT.label)
            self.photos_label = translate_document_name(DocumentType.PHOTOS.label)

        mail.outbox = []

        DocumentRequirement.objects.filter(application_purpose="work").delete()
        DocumentRequirement.objects.create(
            application_purpose="work", document_type=DocumentType.PASSPORT, position=0
        )

    def test_sends_email_when_documents_missing(self):
        sent = send_missing_documents_email(self.client_record)
        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn(self.passport_label, mail.outbox[0].body)

    def test_skips_email_when_nothing_missing(self):
        Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.PASSPORT,
            file=SimpleUploadedFile("passport.pdf", b"content"),
        )

        sent = send_missing_documents_email(self.client_record)
        self.assertEqual(sent, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_includes_uploaded_expiry_details_when_other_docs_missing(self):
        DocumentRequirement.objects.create(
            application_purpose="work",
            document_type=DocumentType.PHOTOS,
            position=1,
        )

        Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.PASSPORT,
            expiry_date=date.today(),
            file=SimpleUploadedFile("passport.pdf", b"content"),
        )

        sent = send_missing_documents_email(self.client_record)

        self.assertEqual(sent, 1)
        self.assertEqual(len(mail.outbox), 2)
        body = mail.outbox[0].body
        self.assertIn(self.passport_label, body)
        self.assertIn(self.photos_label, body)
        self.assertIn(date.today().strftime("%d.%m.%Y"), body)


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

        with translation.override(self.client_record.language):
            self.passport_label = translate_document_name(DocumentType.PASSPORT.label)
            self.photos_label = translate_document_name(DocumentType.PHOTOS.label)

        mail.outbox = []

    def test_uploading_wezwanie_returns_pending_confirmation(self):
        login_successful = self.client.login(username="staff_wezwanie", password="pass")
        self.assertTrue(login_successful)

        content = b"Numer sprawy: ZZ/987/24\nw dniu 05-06-2024 pobrano odciski"
        upload = SimpleUploadedFile("wezwanie.txt", content)
        url = reverse(
            "clients:add_document",
            kwargs={"client_id": self.client_record.pk, "doc_type": "wezwanie"},
        )

        response = self.client.post(
            url,
            {"file": upload, "parse_wezwanie": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["pending_confirmation"])

        updated_client = Client.objects.get(pk=self.client_record.pk)
        self.assertIsNone(updated_client.case_number)
        self.assertIsNone(updated_client.fingerprints_date)

        document = Document.objects.get(client=updated_client, document_type="wezwanie")
        self.assertTrue(document.awaiting_confirmation)

    def test_confirm_wezwanie_updates_client_and_sends_email(self):
        login_successful = self.client.login(username="staff_wezwanie", password="pass")
        self.assertTrue(login_successful)

        content = b"Numer sprawy: ZZ/987/24\nw dniu 05-06-2024 pobrano odciski\n4 zdjecia"
        upload = SimpleUploadedFile("wezwanie.txt", content)
        upload_url = reverse(
            "clients:add_document",
            kwargs={"client_id": self.client_record.pk, "doc_type": "wezwanie"},
        )

        upload_response = self.client.post(
            upload_url,
            {"file": upload, "parse_wezwanie": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        payload = json.loads(upload_response.content)
        document = Document.objects.get(pk=payload["doc_id"])

        confirm_url = reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk})
        response = self.client.post(
            confirm_url,
            {
                "first_name": "Jan",
                "last_name": "Test",
                "case_number": "ZZ/987/24",
                "fingerprints_date": "2024-06-05",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        updated_client = Client.objects.get(pk=self.client_record.pk)
        self.assertEqual(updated_client.case_number, "ZZ/987/24")
        self.assertEqual(updated_client.fingerprints_date, date(2024, 6, 5))

        document.refresh_from_db()
        self.assertFalse(document.awaiting_confirmation)

        self.assertGreaterEqual(len(mail.outbox), 1)
        self.assertIn(self.passport_label, mail.outbox[0].body)
        self.assertIn(self.photos_label, mail.outbox[0].body)


class BulkDocumentVerificationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff_user = user_model.objects.create_user(
            username='checker', password='pass', is_staff=True
        )

        self.client_record = Client.objects.create(
            first_name='Alex',
            last_name='Nowak',
            citizenship='PL',
            phone='+48111111111',
            email='alex@example.com',
        )

        self.unverified_doc = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.PASSPORT,
            file=SimpleUploadedFile('passport.pdf', b'data'),
            verified=False,
        )

        self.verified_doc = Document.objects.create(
            client=self.client_record,
            document_type=DocumentType.PHOTOS,
            file=SimpleUploadedFile('photos.pdf', b'data'),
            verified=True,
        )

    def test_marks_all_documents_verified_and_sends_email_once(self):
        self.client.login(username='checker', password='pass')

        url = reverse('clients:verify_all_documents', kwargs={'client_id': self.client_record.pk})
        with patch('clients.views.documents.send_missing_documents_email') as mock_send:
            mock_send.return_value = 1
            response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)

        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['verified_count'], 1)
        mock_send.assert_called_once_with(self.client_record)

        refreshed = Document.objects.get(pk=self.unverified_doc.pk)
        self.assertTrue(refreshed.verified)

        still_verified = Document.objects.get(pk=self.verified_doc.pk)
        self.assertTrue(still_verified.verified)

    def test_skips_email_when_nothing_to_verify(self):
        Document.objects.filter(pk=self.unverified_doc.pk).update(verified=True)
        self.client.login(username='checker', password='pass')

        url = reverse('clients:verify_all_documents', kwargs={'client_id': self.client_record.pk})
        with patch('clients.views.documents.send_missing_documents_email') as mock_send:
            response = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        self.assertEqual(payload['verified_count'], 0)
        mock_send.assert_not_called()


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
