"""
Тесты реального пользовательского потока (Real User Flow Tests).
"""
import io
import datetime
from decimal import Decimal
from PIL import Image

from django.test import TestCase, Client as TestClient, override_settings
from django.contrib.auth import get_user_model

from clients.models import Client, Payment, Document, DocumentRequirement, Reminder
from clients.constants import DocumentType
from submissions.models import Submission, Document as SubmissionDocument
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()

@override_settings(MEDIA_ROOT='generated_media_test')
class RealUserFlowTest(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_staff', email='admin@legalize.com', password='AdminPass123!', is_staff=True, is_superuser=True
        )
        self.regular_user = User.objects.create_user(username='client_user', email='client@example.com', password='ClientPass123!')
        self.client_profile = Client.objects.create(
            user=self.regular_user, first_name='Ivan', last_name='Petrov', email='client@example.com',
            phone='+48123456789', citizenship='RU', application_purpose='work', language='ru'
        )
        self.http_client = TestClient()

    def test_01_create_new_submission_basis_test(self):
        print("\n[TEST 1] Creating new submission 'test'...")
        self.http_client.force_login(self.admin_user)
        new_submission = Submission.objects.create(
            name='Test Application', name_ru='Тестовое основание', name_pl='Testowa podstawa', name_en='Test Basis'
        )
        self.assertIsNotNone(new_submission.id)
        print(f"[OK] Submission created: {new_submission.slug}")

    def test_02_add_documents_to_submission(self):
        print("\n[TEST 2] Adding documents to submission...")
        submission = Submission.objects.create(name='Test Submission', status=Submission.Status.IN_PROGRESS)
        doc1 = SubmissionDocument.objects.create(submission=submission, title='Passport')
        self.assertEqual(submission.documents.count(), 1)
        print(f"[OK] Added documents to {submission.slug}")

    def test_03_create_requirements_and_change_purpose(self):
        print("\n[TEST 3] Changing client purpose to 'test-application'...")
        submission = Submission.objects.create(name='Test App', slug='test-application')
        
        # Avoid IntegrityError by using a unique purpose or checking existence
        DocumentRequirement.objects.get_or_create(
            application_purpose='test-application',
            document_type=DocumentType.PASSPORT.value,
            defaults={'custom_name_ru': 'Паспорт тест'}
        )
        
        self.client_profile.application_purpose = 'test-application'
        self.client_profile.save()
        self.assertEqual(self.client_profile.application_purpose, 'test-application')
        print("[OK] Client purpose changed to 'test-application'")

    def test_04_payment_and_reminders(self):
        print("\n[TEST 4] Testing payments and reminders...")
        payment = Payment.objects.create(
            client=self.client_profile, service_description='work_service', total_amount=Decimal('1000.00'), status='pending'
        )
        payment.amount_paid = Decimal('500.00')
        payment.status = 'partial'
        payment.due_date = datetime.date.today()
        payment.save()
        
        reminder = Reminder.objects.filter(payment=payment).first()
        self.assertIsNotNone(reminder)
        print("[OK] Payment partial and reminder created.")

    def test_05_image_compression_webp(self):
        print("\n[TEST 5] Testing image compression to WebP...")
        img_io = io.BytesIO()
        Image.new('RGB', (100, 100), color='red').save(img_io, format='JPEG')
        img_io.seek(0)
        uploaded_file = SimpleUploadedFile(name='test.jpg', content=img_io.getvalue(), content_type='image/jpeg')
        
        doc = Document.objects.create(client=self.client_profile, document_type=DocumentType.PASSPORT.value, file=uploaded_file)
        self.assertTrue(doc.file.name.endswith('.webp'))
        print(f"[OK] Image compressed to WebP: {doc.file.name}")

    def test_06_complex_workflow(self):
        print("\n[TEST 6] Complex workflow: new client, payment, purpose change...")
        user = User.objects.create_user(username='dmitry', email='d@ex.com', password='p')
        client = Client.objects.create(user=user, first_name='Dmitry', application_purpose='work')
        
        payment = Payment.objects.create(client=client, service_description='work_service', total_amount=Decimal('3000'), status='pending')
        
        # Change to study
        client.application_purpose = 'study'
        client.save()
        payment.refresh_from_db()
        self.assertEqual(payment.service_description, 'study_service')
        print("[OK] Complex workflow: purpose sync worked")

class ParserLogicTest(TestCase):
    def test_normalization(self):
        val = Client.normalize_case_number(" wsc - 123 ")
        self.assertEqual(val, "WSC-123")
        print(f"[OK] Normalization: ' wsc - 123 ' -> {val}")

    def test_hashing(self):
        h1 = Client.hash_case_number("WSC123")
        h2 = Client.hash_case_number("wsc 123")
        self.assertEqual(h1, h2)
        print("[OK] Hashing consistent")
