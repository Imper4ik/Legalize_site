import json
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from clients.models import Client, Document
from clients.constants import DocumentType

User = get_user_model()


class DocumentViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        self.client_obj = Client.objects.create(
            first_name="Ivan",
            last_name="Ivanov",
            email="ivan@example.com",
            phone="123456789",
        )
        self.client = DjangoClient()
        self.client.login(email="staff@example.com", password="password123")

        # Create a sample document
        self.sample_file = SimpleUploadedFile(
            "test_doc.jpg",
            b"file_content",
            content_type="image/jpeg"
        )
        self.document = Document.objects.create(
            client=self.client_obj,
            document_type=DocumentType.PASSPORT,
            file=self.sample_file
        )

    def test_update_client_notes(self):
        url = reverse('clients:update_client_notes', kwargs={'pk': self.client_obj.pk})
        response = self.client.post(url, data={'notes': 'New note'})
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.notes, 'New note')
        
    def test_update_client_notes_json(self):
        url = reverse('clients:update_client_notes', kwargs={'pk': self.client_obj.pk})
        response = self.client.post(url, data={'notes': 'New JSON note'}, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        self.client_obj.refresh_from_db()
        self.assertEqual(self.client_obj.notes, 'New JSON note')
        self.assertEqual(response.json().get('status'), 'success')

    def test_add_document_get(self):
        url = reverse('clients:add_document', kwargs={'client_id': self.client_obj.pk, 'doc_type': 'health_insurance'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'clients/add_document.html')

    def test_add_document_post(self):
        url = reverse('clients:add_document', kwargs={'client_id': self.client_obj.pk, 'doc_type': 'health_insurance'})
        test_file = SimpleUploadedFile("insurance.jpg", b"abc", content_type="image/jpeg")
        response = self.client.post(url, data={'file': test_file})
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.assertTrue(Document.objects.filter(client=self.client_obj, document_type='health_insurance').exists())

    def test_document_delete(self):
        url = reverse('clients:document_delete', kwargs={'pk': self.document.pk})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())

    def test_toggle_document_verification(self):
        url = reverse('clients:toggle_document_verification', kwargs={'doc_id': self.document.pk})
        self.assertFalse(self.document.verified)
        response = self.client.post(url)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        self.document.refresh_from_db()
        self.assertTrue(self.document.verified)

    def test_toggle_document_verification_json(self):
        url = reverse('clients:toggle_document_verification', kwargs={'doc_id': self.document.pk})
        self.document.verified = False
        self.document.save()
        
        response = self.client.post(url, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.document.refresh_from_db()
        self.assertTrue(self.document.verified)

    def test_verify_all_documents(self):
        # Create unverified docs
        Document.objects.create(client=self.client_obj, document_type='work_contract', file=SimpleUploadedFile("1.jpg", b"a"))
        Document.objects.create(client=self.client_obj, document_type='visa', file=SimpleUploadedFile("2.jpg", b"a"))
        
        url = reverse('clients:verify_all_documents', kwargs={'client_id': self.client_obj.id})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('clients:client_detail', kwargs={'pk': self.client_obj.pk}))
        
        unverified_count = Document.objects.filter(client=self.client_obj, verified=False).count()
        self.assertEqual(unverified_count, 0)

    def test_client_status_api(self):
        url = reverse('clients:client_status_api', kwargs={'pk': self.client_obj.id})
        response = self.client.get(url, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('checklist_html', data)

    def test_client_overview_partial(self):
        url = reverse('clients:client_overview_partial', kwargs={'pk': self.client_obj.id})
        response = self.client.get(url, HTTP_ACCEPT='application/json', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('html', data)

    def test_client_checklist_partial(self):
        url = reverse('clients:client_checklist_partial', kwargs={'pk': self.client_obj.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'clients/partials/document_checklist.html')
