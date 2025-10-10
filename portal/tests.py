import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from django.contrib.auth import get_user_model

from clients.models import Client, Document


class PortalDocumentUploadTests(TestCase):
    def setUp(self):
        User = get_user_model()
        unique_suffix = uuid.uuid4().hex[:8]
        self.user = User.objects.create_user(
            username=f'client-user-{unique_suffix}',
            email=f'client{unique_suffix}@example.com',
            password='secret123'
        )
        self.client_profile = self.user.client_profile
        self.client_profile.first_name = 'Test'
        self.client_profile.last_name = 'User'
        self.client_profile.citizenship = 'PL'
        self.client_profile.phone = '123456789'
        self.client_profile.application_purpose = 'study'
        self.client_profile.language = 'ru'
        self.client_profile.status = 'new'
        self.client_profile.has_checklist_access = True
        self.client_profile.save()
        self.client.force_login(self.user)
        translation.activate('ru')
        self.addCleanup(translation.deactivate)
        self.upload_url = reverse('portal:portal_document_upload', args=['passport'])

    def _make_file(self, name='passport.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4 test content', content_type='application/pdf')

    def test_ajax_upload_returns_json_success(self):
        response = self.client.post(
            self.upload_url,
            data={'file': self._make_file()},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        payload = response.json()
        self.assertEqual(payload['status'], 'success')
        self.assertTrue(Document.objects.filter(client=self.client_profile, document_type='passport').exists())

    def test_accept_header_triggers_ajax_detection(self):
        response = self.client.post(
            self.upload_url,
            data={'file': self._make_file('passport2.pdf')},
            HTTP_ACCEPT='application/json'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(response.json()['status'], 'success')

    def test_non_ajax_request_redirects(self):
        response = self.client.post(self.upload_url, data={'file': self._make_file('passport3.pdf')})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith(reverse('portal:profile_detail')))

    def test_invalid_upload_returns_json_errors(self):
        response = self.client.post(self.upload_url, data={}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response['Cache-Control'], 'no-store')
        payload = response.json()
        self.assertEqual(payload['status'], 'error')
        self.assertIn('file', payload['errors'])
