from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clients.models import Client, ClientOnboardingSession, Document, MOSApplicationData
from clients.services.onboarding_tokens import hash_onboarding_token

class OnboardingPassportUploadTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(email="test_passport_onb@example.com", password="secure_pwd_123")
        self.client_obj = Client.objects.create(
            first_name="Jan",
            last_name="Kowalski",
            email="jan@example.com",
            phone="+48600111222",
            user=self.user,
            application_purpose="study",
            language="ru",
        )
        self.mos_data, _ = MOSApplicationData.objects.get_or_create(client=self.client_obj)
        self.mos_data.status = "client_filling"
        self.mos_data.personal_data = {"first_name": "Jan", "last_name": "Kowalski"}
        self.mos_data.passport_data = {}
        self.mos_data.save()
        self.token = "passport-token-123"
        self.session = ClientOnboardingSession.objects.create(
            client=self.client_obj,
            token_hash=hash_onboarding_token(self.token),
            status="created",
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_login(self.user)

    def test_get_passport_page_shows_upload_card_and_inputs(self):
        from django.utils import translation
        with translation.override('ru'):
            url = reverse("clients:onboarding_passport", kwargs={"token": self.token})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Загрузить скан загранпаспорта")
            self.assertContains(response, 'name="passport_file"')
            self.assertContains(response, 'id="first_name"')

    def test_upload_passport_scan_creates_document_and_triggers_ocr(self):
        from django.utils import translation
        with translation.override('ru'):
            url = reverse("clients:onboarding_passport", kwargs={"token": self.token})
            from io import BytesIO
            from PIL import Image
            buffer = BytesIO()
            image = Image.new("RGB", (20, 20), "white")
            image.save(buffer, format="PNG")
            file_data = SimpleUploadedFile("passport.png", buffer.getvalue(), content_type="image/png")
            
            response = self.client.post(url, {
                "action": "upload_passport",
                "passport_file": file_data,
            })
            
            if response.status_code != 302 or response.url != url:
                print("DEBUG: status_code =", response.status_code)
                print("DEBUG: redirect url =", getattr(response, 'url', None))
                if hasattr(response, 'context'):
                    print("DEBUG: form errors =", response.context.get('form', {}).errors if response.context else None)
            
            # Should redirect back to the passport page to let client view the form and details
            self.assertRedirects(response, url)
            
            # Check that the Document object was created
            passport_docs = Document.objects.filter(client=self.client_obj, document_type="passport")
            self.assertEqual(passport_docs.count(), 1)
            doc = passport_docs.first()
            self.assertTrue(doc.file.name.endswith(".webp"))
            # Since it is a passport upload, OCR processing job should have been created
            from clients.models import DocumentProcessingJob
            jobs = DocumentProcessingJob.objects.filter(document=doc)
            self.assertTrue(jobs.exists())
            self.assertEqual(jobs.first().job_type, DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR)

    def test_post_passport_data_manually_saves_data_and_redirects(self):
        from django.utils import translation
        with translation.override('ru'):
            url = reverse("clients:onboarding_passport", kwargs={"token": self.token})
            
            response = self.client.post(url, {
                "first_name": "Janusz",
                "last_name": "Kowalski",
                "phone": "+48600111222",
                "email": "jan@example.com",
                "birth_date": "1990-01-01",
                "citizenship": "Belarus",
                "gender": "M",
                "document_number": "AB1234567",
                "expiry_date": "2030-01-01",
                "issue_date": "2020-01-01",
                "issuing_authority": "MVD 123",
            })
            
            # Should redirect to personal extra page
            self.assertRedirects(response, reverse("clients:onboarding_personal_extra", kwargs={"token": self.token}))
            
            # Verify saved data
            self.mos_data.refresh_from_db()
            self.assertEqual(self.mos_data.personal_data["first_name"], "Janusz")
            self.assertEqual(self.mos_data.personal_data["citizenship"], "Belarus")
            self.assertEqual(self.mos_data.passport_data["document_number"], "AB1234567")
            self.assertEqual(self.mos_data.passport_data["issuing_authority"], "MVD 123")

    def test_upload_passport_from_dashboard_creates_document_and_triggers_ocr(self):
        from django.utils import translation
        with translation.override('ru'):
            url = reverse("clients:onboarding_document_upload", kwargs={"token": self.token, "doc_type": "passport"})
            from io import BytesIO
            from PIL import Image
            buffer = BytesIO()
            image = Image.new("RGB", (20, 20), "white")
            image.save(buffer, format="PNG")
            file_data = SimpleUploadedFile("passport_dash.png", buffer.getvalue(), content_type="image/png")
            
            response = self.client.post(url, {
                "file": file_data,
            })
            
            # Should redirect back to the start page
            self.assertRedirects(response, reverse("clients:onboarding_start", kwargs={"token": self.token}) + "#doc-passport")
            
            # Check that the Document object was created
            passport_docs = Document.objects.filter(client=self.client_obj, document_type="passport")
            self.assertEqual(passport_docs.count(), 1)
            doc = passport_docs.first()
            self.assertTrue(doc.file.name.endswith(".webp"))
            
            # Check OCR job was created
            from clients.models import DocumentProcessingJob
            jobs = DocumentProcessingJob.objects.filter(document=doc)
            self.assertTrue(jobs.exists())
            self.assertEqual(jobs.first().job_type, DocumentProcessingJob.JOB_TYPE_PASSPORT_OCR)

