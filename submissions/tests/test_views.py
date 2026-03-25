from django.test import TestCase, Client as DjangoClient
from django.urls import reverse
from django.contrib.auth import get_user_model
from submissions.models import Submission, Document
import json

User = get_user_model()


class SubmissionViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        self.client = DjangoClient()
        self.client.login(email="staff@example.com", password="password123")
        
        self.submission = Submission.objects.create(
            name="Test Submission",
            status="draft"
        )

    def test_submission_list_view(self):
        url = reverse('submissions:submission_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'submissions/submission_list.html')
        self.assertIn(self.submission, response.context['submissions'])

    def test_submission_create_view_get(self):
        url = reverse('submissions:submission_create')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'submissions/submission_form.html')

    def test_submission_create_view_post(self):
        url = reverse('submissions:submission_create')
        data = {'name': 'New Submission', 'status': 'in_progress'}
        response = self.client.post(url, data=data)
        new_submission = Submission.objects.get(name='New Submission')
        self.assertRedirects(response, reverse('submissions:submission_detail', kwargs={'pk': new_submission.pk}))

    def test_submission_quick_create(self):
        url = reverse('submissions:submission_quick_create')
        data = {'name': 'Quick Submission', 'status': 'draft'}
        response = self.client.post(url, data=data)
        self.assertTrue(Submission.objects.filter(name='Quick Submission').exists())
        # Should redirect back to referer or checklist manage
        self.assertEqual(response.status_code, 302)

    def test_submission_quick_update(self):
        url = reverse('submissions:submission_quick_update', kwargs={'submission_id': self.submission.id})
        data = {'name': 'Updated Name', 'status': 'completed'}
        response = self.client.post(url, data=data)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.name, 'Updated Name')
        self.assertEqual(self.submission.status, 'completed')
        self.assertEqual(response.status_code, 302)

    def test_submission_quick_delete(self):
        url = reverse('submissions:submission_quick_delete', kwargs={'submission_id': self.submission.id})
        response = self.client.post(url)
        self.assertFalse(Submission.objects.filter(id=self.submission.id).exists())
        self.assertEqual(response.status_code, 302)

    def test_submission_detail_view(self):
        url = reverse('submissions:submission_detail', kwargs={'pk': self.submission.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'submissions/submission_detail.html')
        self.assertEqual(response.context['submission'], self.submission)


class DocumentViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        self.client = DjangoClient()
        self.client.login(email="staff@example.com", password="password123")
        
        self.submission = Submission.objects.create(
            name="Test Submission",
            status="draft"
        )
        self.document = Document.objects.create(
            submission=self.submission,
            title="Test Doc",
            status="not_uploaded"
        )

    def test_document_create_view_get(self):
        url = reverse('submissions:document_create', kwargs={'submission_id': self.submission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'submissions/document_form.html')

    def test_document_create_view_post(self):
        url = reverse('submissions:document_create', kwargs={'submission_id': self.submission.id})
        data = {'title': 'New Doc', 'status': 'not_uploaded'}
        response = self.client.post(url, data=data)
        self.assertRedirects(response, reverse('submissions:submission_detail', kwargs={'pk': self.submission.pk}))
        self.assertTrue(Document.objects.filter(title='New Doc', submission=self.submission).exists())

    def test_document_update_view_get(self):
        url = reverse('submissions:document_edit', kwargs={'pk': self.document.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'submissions/document_form.html')

    def test_document_update_view_post(self):
        url = reverse('submissions:document_edit', kwargs={'pk': self.document.pk})
        data = {'title': 'Updated Doc', 'status': 'not_uploaded'}
        response = self.client.post(url, data=data)
        self.assertRedirects(response, reverse('submissions:submission_detail', kwargs={'pk': self.submission.pk}))
        self.document.refresh_from_db()
        self.assertEqual(self.document.title, 'Updated Doc')

    def test_document_delete_view_post(self):
        url = reverse('submissions:document_delete', kwargs={'pk': self.document.pk})
        response = self.client.post(url)
        self.assertRedirects(response, reverse('submissions:submission_detail', kwargs={'pk': self.submission.pk}))
        self.assertFalse(Document.objects.filter(id=self.document.id).exists())


class ApiViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_superuser(
            username="staff_admin", email="staff@example.com", password="password123"
        )
        self.client = DjangoClient()
        self.client.login(email="staff@example.com", password="password123")
        
        self.submission = Submission.objects.create(
            name="API Submission",
            status="draft"
        )
        self.document = Document.objects.create(
            submission=self.submission,
            title="API Doc",
            status="not_uploaded"
        )

    def test_submission_api_get(self):
        url = reverse('submissions:api_submission_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(any(s['id'] == self.submission.id for s in data['items']))

    def test_submission_api_post(self):
        url = reverse('submissions:api_submission_list')
        data = {'name': 'New API Sub', 'status': 'draft'}
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Submission.objects.filter(name='New API Sub').exists())

    def test_submission_api_post_invalid(self):
        url = reverse('submissions:api_submission_list')
        data = {'name': '', 'status': 'draft'}
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['status'], 'error')

    def test_submission_detail_api_get(self):
        url = reverse('submissions:api_submission_detail', kwargs={'pk': self.submission.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['submission']['id'], self.submission.id)

    def test_submission_detail_api_delete(self):
        url = reverse('submissions:api_submission_detail', kwargs={'pk': self.submission.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.filter(id=self.submission.id).exists())

    def test_document_api_get(self):
        url = reverse('submissions:api_document_list', kwargs={'submission_id': self.submission.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(any(d['id'] == self.document.id for d in data['items']))

    def test_document_api_post(self):
        url = reverse('submissions:api_document_list', kwargs={'submission_id': self.submission.id})
        data = {'title': 'API New Doc', 'status': 'not_uploaded'}
        response = self.client.post(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Document.objects.filter(title='API New Doc').exists())

    def test_document_api_post_invalid_json(self):
        url = reverse('submissions:api_document_list', kwargs={'submission_id': self.submission.id})
        response = self.client.post(url, data="invalid json", content_type='application/json')
        # ResponseHelper.error 400
        self.assertEqual(response.status_code, 400)

    def test_document_detail_api_patch(self):
        url = reverse('submissions:api_document_detail', kwargs={'pk': self.document.pk})
        data = {'title': 'Patched Doc'}
        response = self.client.patch(url, data=json.dumps(data), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.title, 'Patched Doc')

    def test_document_detail_api_delete(self):
        url = reverse('submissions:api_document_detail', kwargs={'pk': self.document.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.filter(id=self.document.id).exists())
