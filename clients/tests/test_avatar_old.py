import json
import tempfile
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from gettext import GNUTranslations
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation
from reportlab.pdfgen import canvas

import shutil

from allauth.account.models import EmailAddress

from clients.forms import DocumentChecklistForm, DocumentRequirementAddForm, DocumentRequirementEditForm
from clients.models import Client, Document, DocumentRequirement, translate_document_name
from clients.tests.factories import create_manager_user, create_staff_user
from clients.constants import DOCUMENT_CHECKLIST, DocumentType
from clients.services.notifications import send_missing_documents_email
from clients.services.responses import NO_STORE_HEADER, ResponseHelper
from clients.services.wezwanie_parser import WezwanieData, parse_wezwanie


def _build_pdf_upload(name: str, text: str = "wezwanie test") -> SimpleUploadedFile:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="application/pdf")

class PurePythonMsgfmtTests(SimpleTestCase):
    def test_compiled_mo_file_is_valid_utf8(self):
        from legalize_site.utils.i18n import _write_mo_file

        tmp_root = Path(__file__).resolve().parents[2] / "tmp"
        tmp_root.mkdir(exist_ok=True)
        tmp = tmp_root / f"msgfmt-{uuid.uuid4().hex}"
        try:
            tmp.mkdir(parents=True)
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
                        'msgstr "\u043f\u0440\u0438\u0432\u0435\u0442"',
                    ]
                ),
                encoding="utf-8",
            )

            mo_path = po_path.with_suffix(".mo")
            _write_mo_file(po_path, mo_path)

            with mo_path.open("rb") as fp:
                translations = GNUTranslations(fp)

            self.assertEqual(translations.gettext("hello"), "\u043f\u0440\u0438\u0432\u0435\u0442")
            self.assertEqual(translations.gettext("missing"), "missing")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CalculatorViewTests(TestCase):
    def setUp(self):
        self.staff_user = create_staff_user(email='staff@example.com')

    def test_months_in_period_multiplies_tuition_total(self):
        login_successful = self.client.login(email='staff@example.com', password='pass')
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
        self.staff_user = create_staff_user(email='staff@example.com')

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
        login_successful = self.client.login(email='staff@example.com', password='pass')
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
        login_successful = self.client.login(email='staff@example.com', password='pass')
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
        from django.contrib.auth import get_user_model
        self.user_model = get_user_model()

    def test_deleting_client_deactivates_linked_user_account(self):
        user = self.user_model.objects.create_user(
            email='client@example.com', password='secret123'
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

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(self.user_model.objects.filter(pk=user.pk).exists())
        self.assertTrue(EmailAddress.objects.filter(email='client@example.com').exists())

    def test_staff_accounts_are_preserved_when_client_deleted(self):
        staff_user = self.user_model.objects.create_user(
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
        required_codes = [code for code, _label in required]
        self.assertGreaterEqual(len(required_codes), 2)
        self.assertEqual(required_codes[0], DocumentType.PHOTOS.value)
        self.assertEqual(required_codes[1], DocumentType.PASSPORT.value)

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
        form = DocumentRequirementAddForm(
            data={'name': '\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0441\u043f\u0440\u0430\u0432\u043a\u0430'},
            purpose='work',
        )

        self.assertTrue(form.is_valid())
        requirement = form.save()

        self.assertEqual(requirement.document_type, '\u0434\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f_\u0441\u043f\u0440\u0430\u0432\u043a\u0430')
        self.assertEqual(requirement.custom_name, '\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0441\u043f\u0440\u0430\u0432\u043a\u0430')
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
            application_purpose='work', document_type=DocumentType.PASSPORT, custom_name='\u041f\u0430\u0441\u043f\u043e\u0440\u0442', position=0
        )

        form = DocumentRequirementEditForm(
            data={'custom_name': '\u041f\u0430\u0441\u043f\u043e\u0440\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u0430', 'is_required': False},
            instance=requirement,
        )

        self.assertTrue(form.is_valid())
        updated = form.save()

        self.assertFalse(updated.is_required)
        self.assertEqual(updated.custom_name, '\u041f\u0430\u0441\u043f\u043e\u0440\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u0430')


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
        required_codes = [code for code, _label in required]
        self.assertIn(DocumentType.PASSPORT.value, required_codes)
        self.assertIn(DocumentType.ENROLLMENT_CERTIFICATE.value, required_codes)

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
        self.staff_user = create_staff_user(email="staff_wezwanie@example.com")

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
        login_successful = self.client.login(email="staff_wezwanie@example.com", password="pass")
        self.assertTrue(login_successful)

        upload = _build_pdf_upload("wezwanie.pdf")
        url = reverse(
            "clients:add_document",
            kwargs={"client_id": self.client_record.pk, "doc_type": "wezwanie"},
        )

        with patch("clients.views.documents.parse_wezwanie") as parse_mock:
            parse_mock.return_value = WezwanieData(
                text="Numer sprawy: ZZ/987/24",
                case_number="ZZ/987/24",
                fingerprints_date=date(2024, 6, 5),
                full_name="Jan Test",
                wezwanie_type="fingerprints",
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
        login_successful = self.client.login(email="staff_wezwanie@example.com", password="pass")
        self.assertTrue(login_successful)

        upload = _build_pdf_upload("wezwanie.pdf")
        upload_url = reverse(
            "clients:add_document",
            kwargs={"client_id": self.client_record.pk, "doc_type": "wezwanie"},
        )

        with patch("clients.views.documents.parse_wezwanie") as parse_mock:
            parse_mock.return_value = WezwanieData(
                text="Numer sprawy: ZZ/987/24",
                case_number="ZZ/987/24",
                fingerprints_date=date(2024, 6, 5),
                full_name="Jan Test",
                wezwanie_type="fingerprints",
                required_documents=[DocumentType.PHOTOS.value],
            )
            upload_response = self.client.post(
                upload_url,
                {"file": upload, "parse_wezwanie": "1"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        payload = json.loads(upload_response.content)
        document = Document.objects.get(pk=payload["doc_id"])

        confirm_url = reverse("clients:confirm_wezwanie_parse", kwargs={"doc_id": document.pk})
        with patch("clients.views.documents.parse_wezwanie") as parse_mock:
            parse_mock.return_value = WezwanieData(
                text="Numer sprawy: ZZ/987/24",
                case_number="ZZ/987/24",
                fingerprints_date=date(2024, 6, 5),
                full_name="Jan Test",
                wezwanie_type="fingerprints",
                required_documents=[DocumentType.PHOTOS.value],
            )
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
        self.staff_user = create_staff_user(email='checker@example.com')

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
        self.client.login(email='checker@example.com', password='pass')

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
        self.client.login(email='checker@example.com', password='pass')

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

class ClientViewsTestCase(TestCase):
    def setUp(self):
        self.staff_user = create_manager_user(email='staff@example.com')
        self.client_record = Client.objects.create(
            first_name='Ivan',
            last_name='Ivanov',
            email='ivan_new@example.com',
            phone='+48123456789',
            citizenship='UA',
        )

    def test_client_detail_renders_and_contains_service_choices(self):
        self.client.login(email='staff@example.com', password='pass')
        url = reverse('clients:client_detail', kwargs={'pk': self.client_record.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('service_choices', response.context)
        choices = response.context['service_choices']
        self.assertTrue(any(choice[0] == 'study_service' for choice in choices))

    def test_add_payment_creates_payment(self):
        self.client.login(email='staff@example.com', password='pass')
        url = reverse('clients:add_payment', kwargs={'client_id': self.client_record.pk})
        
        response_invalid = self.client.post(url, {}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response_invalid.status_code, 400)
        payload = json.loads(response_invalid.content)
        self.assertEqual(payload['status'], 'error')
        
        response_valid = self.client.post(url, {
            'service_description': 'work_service',
            'total_amount': '1500.00',
            'amount_paid': '0',
            'status': 'pending',
            'payment_method': 'card',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response_valid.status_code, 200)
        payload = json.loads(response_valid.content)
        self.assertEqual(payload['status'], 'success')
        self.assertIn('payment_id', payload)
        
        payment = self.client_record.payments.first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.total_amount, Decimal('1500.00'))
