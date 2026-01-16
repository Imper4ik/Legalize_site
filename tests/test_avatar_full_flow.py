import io
import datetime
from decimal import Decimal
from PIL import Image
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation
from django.core.files.uploadedfile import SimpleUploadedFile

from clients.models import Client, Payment, Reminder, Document, DocumentRequirement
from clients.constants import DocumentType
from clients.services.wezwanie_parser import WezwanieData

User = get_user_model()


@override_settings(MEDIA_ROOT='generated_media_test')
class AvatarFullFlowTest(TestCase):
    """
    "Avatar" System Integrations Test Suite.
    
    This test suite acts as an automated agent (Avatar) that traverses the entire
    application lifecycle to verify deep integrations, signals, and synchronization logic.
    """

    def setUp(self):
        # 1. Create a User (Registration Simulation)
        self.email = "avatar@example.com"
        self.password = "ComplexPass123!"
        self.user = User.objects.create_user(username='avatar', email=self.email, password=self.password)
        
        
        # 2. Creates Client explicitly (since signal requires specific fields often handled by forms)
        # 2. Creates Client explicitly (since signal requires specific fields often handled by forms)
        self.client_profile, created = Client.objects.get_or_create(
            user=self.user,
            defaults={
                "first_name": "Avatar",
                "last_name": "Tester",
                "email": self.email,
                "phone": "+123456789",
                "citizenship": "Testland",
                "application_purpose": "work"
            }
        )
        if not created:
             self.client_profile.application_purpose = "work"
             self.client_profile.save()

    def test_01_client_lifecycle_and_deletion_sync(self):
        """Verify Client <-> User deletion synchronization."""
        print("\n[Avatar]: Testing User/Client deletion sync...")
        
        user_id = self.user.id
        client_id = self.client_profile.id
        
        # Delete Client
        self.client_profile.delete()
        
        # Check if User is also deleted (Signal: delete_user_account_when_client_removed)
        with self.assertRaises(User.DoesNotExist):
            User.objects.get(id=user_id)
            
        print("[OK] Client deletion correctly removed User account.")

    def test_02_payment_synchronization_with_purpose(self):
        """Verify Payment service type updates when Client purpose changes."""
        print("\n[Avatar]: Testing Payment <-> Purpose synchronization...")
        
        # Create a PENDING payment
        payment = Payment.objects.create(
            client=self.client_profile,
            total_amount=Decimal("1000.00"),
            status='pending',
            service_description='work_service'  # Match initial purpose 'work'
        )
        
        # Create a PAID payment (should NOT change)
        paid_payment = Payment.objects.create(
            client=self.client_profile,
            total_amount=Decimal("500.00"),
            status='paid',
            service_description='work_service'
        )
        
        # Change Client Purpose to 'study'
        self.client_profile.application_purpose = "study"
        self.client_profile.save()  # Triggers signal: sync_payment_service_check
        
        # Reload payments
        payment.refresh_from_db()
        paid_payment.refresh_from_db()
        
        self.assertEqual(payment.service_description, 'study_service', 
                         "Pending payment service should update to 'study_service'")
        self.assertEqual(paid_payment.service_description, 'work_service', 
                         "Paid payment service should NOT change")
        
        print("[OK] Payment service synchronized with Client purpose change.")

    def test_03_payment_reminders_sync(self):
        """Verify Reminder creation/deletion on Payment changes."""
        print("\n[Avatar]: Testing Payment <-> Reminder synchronization...")
        
        payment = Payment.objects.create(
            client=self.client_profile,
            total_amount=Decimal("2000.00"),
            status='pending',
            service_description='work_service'
        )
        
        # 1. No reminder for pending payment without due_date
        self.assertFalse(Reminder.objects.filter(payment=payment).exists())
        
        # 2. Change to Partial + Add Due Date -> Should create Reminder
        today = datetime.date.today()
        payment.status = 'partial'
        payment.due_date = today
        payment.save() # Triggers signal
        
        reminder = Reminder.objects.filter(payment=payment).first()
        self.assertIsNotNone(reminder, "Reminder should be created for partial payment with due_date")
        self.assertEqual(reminder.due_date, today)
        self.assertIn("Второй платёж", reminder.title)
        
        # 3. Delete Payment -> Should delete Reminder
        payment_id = payment.id
        payment.delete() # Triggers signal
        self.assertFalse(Reminder.objects.filter(payment_id=payment_id).exists(), 
                         "Reminder should be deleted when Payment is deleted")
        
        print("[OK] Reminders correctly sync with Payment lifecycle.")

    def test_04_document_compression_and_format(self):
        """Verify creating a document compresses image and converts to WebP."""
        print("\n[Avatar]: Testing Document compression (JPEG -> WEBP)...")
        
        # Generate a dummy JPEG image in memory
        img_io = io.BytesIO()
        image = Image.new('RGB', (2500, 2500), color='red') # Large image
        image.save(img_io, format='JPEG')
        img_io.seek(0)
        
        uploaded_file = SimpleUploadedFile(
            name='test_image.jpg',
            content=img_io.getvalue(),
            content_type='image/jpeg'
        )
        
        doc = Document.objects.create(
            client=self.client_profile,
            document_type=DocumentType.PASSPORT.value,
            file=uploaded_file
        )
        
        # Verify file changed to WebP and name updated
        self.assertTrue(doc.file.name.endswith('.webp'), f"File extension should be .webp, got {doc.file.name}")
        
        # Verify resizing (should be max 2000x2000)
        with doc.file.open('rb') as f:
            saved_img = Image.open(f)
            self.assertTrue(saved_img.width <= 2000, "Image width should be <= 2000")
            self.assertTrue(saved_img.height <= 2000, "Image height should be <= 2000")
            self.assertEqual(saved_img.format, 'WEBP', "Image format should be WEBP")
            
        print("[OK] Image compression and WebP conversion successful.")

    @patch('clients.views.documents.parse_wezwanie')
    def test_05_wezwanie_parsing_integration(self, mock_parse):
        """Verify Wezwanie upload triggers parser and confirmation updates Client fields."""
        print("\n[Avatar]: Testing Wezwanie parsing integration...")
        
        # Mock Parser Result
        mock_result = WezwanieData(
            text="Mock Text",
            case_number="WSC-TEST-123",
            fingerprints_date=datetime.date(2025, 5, 20),
            full_name="Jan Kowalski",
            wezwanie_type="fingerprints"
        )
        mock_parse.return_value = mock_result
        
        # Login as staff (Simulate View)
        # Note: Document upload is view-logic heavy, simpler to test Logic here directly
        # or simulate View if we want. Let's verify the Logic that SHOULD happen in View,
        # but re-implement minimal logic or use Client.
        
        # actually, let's test the VIEW itself to be true Integrations Test
        staff_user = User.objects.create_user(username='staff', email='staff@admin.com', password='pass', is_staff=True)
        self.client.force_login(staff_user) # Django Test Client (implicit self.client from TestCase is HTTP client)
        
        # Wait, TestCase has self.client as HTTP client. My model is self.client (renamed).
        # Let's rename model instance.
        db_client = self.client_profile 
        http_client = self.client_class()
        http_client.force_login(staff_user)
        
        # Upload Wezwanie
        img_io = io.BytesIO(b"fake_pdf_content")
        uploaded_file = SimpleUploadedFile("wezwanie.pdf", b"pdf_data", content_type="application/pdf")
        
        # Clear name to test parser update logic (view only updates empty names)
        self.client_profile.first_name = ""
        self.client_profile.last_name = ""
        self.client_profile.save()
        
        with translation.override('pl'):
            url = reverse('clients:add_document', args=[self.client_profile.id, DocumentType.WEZWANIE.value])
            if not url.endswith('/'):
                url += '/'
            
        response = http_client.post(
            url,
            {
                'file': uploaded_file,
                'document_type': DocumentType.WEZWANIE.value,
                'parse_wezwanie': '1',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            secure=True,
        )
        
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        document = Document.objects.get(pk=payload['doc_id'])
        self.assertTrue(document.awaiting_confirmation)

        # Ensure parser was called for preview
        mock_parse.assert_called_once()

        confirm_url = reverse('clients:confirm_wezwanie_parse', kwargs={'doc_id': document.pk})
        confirm_response = http_client.post(
            confirm_url,
            {
                'first_name': 'Jan',
                'last_name': 'Kowalski',
                'case_number': 'WSC-TEST-123',
                'fingerprints_date': '2025-05-20',
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            secure=True,
        )
        self.assertEqual(confirm_response.status_code, 200)

        # Check if DB Client was updated
        db_client.refresh_from_db()
        self.assertEqual(db_client.case_number, "WSC-TEST-123")
        self.assertEqual(db_client.fingerprints_date, datetime.date(2025, 5, 20))
        self.assertEqual(db_client.first_name, "Jan") # Split from "Jan Kowalski"
        self.assertEqual(db_client.last_name, "Kowalski")

        document.refresh_from_db()
        self.assertFalse(document.awaiting_confirmation)
        self.assertEqual(mock_parse.call_count, 2)
        print("[OK] Wezwanie parsing successfully updated Client profile.")

    def test_06_unified_translations_db(self):
        """Verify translations are pulled from DB custom_names."""
        print("\n[Avatar]: Testing Unified Translations (DB-based)...")
        
        # Set specific custom translations for Passport
        doc_req = DocumentRequirement.objects.get(document_type=DocumentType.PASSPORT.value, application_purpose='work')
        doc_req.custom_name_pl = "Polski Paszport Test"
        doc_req.custom_name_ru = "Русский Паспорт Тест"
        doc_req.custom_name_en = "English Passport Test"
        doc_req.save()
        
        # Test PL
        with translation.override('pl'):
            checklist = self.client_profile.get_document_checklist()
            # Check if our custom name is present
            passport_item = next(item for item in checklist if item['code'] == DocumentType.PASSPORT.value)
            self.assertEqual(passport_item['name'], "Polski Paszport Test")

        # Test RU
        with translation.override('ru'):
            checklist = self.client_profile.get_document_checklist()
            passport_item = next(item for item in checklist if item['code'] == DocumentType.PASSPORT.value)
            self.assertEqual(passport_item['name'], "Русский Паспорт Тест")
            
        print("[OK] Translations correctly loaded from Database custom fields.")
