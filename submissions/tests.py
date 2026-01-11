from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from .models import Submission, Document

User = get_user_model()

class SubmissionModelTest(TestCase):
    def setUp(self):
        self.submission = Submission.objects.create(name="Test Submission")

    def test_submission_creation(self):
        self.assertEqual(self.submission.name, "Test Submission")
        self.assertEqual(self.submission.status, Submission.Status.DRAFT)
        self.assertTrue(self.submission.slug)
    
    def test_slug_generation(self):
        s2 = Submission.objects.create(name="Test Submission")
        self.assertNotEqual(self.submission.slug, s2.slug)

class DocumentModelTest(TestCase):
    def setUp(self):
        self.submission = Submission.objects.create(name="Doc Submission")
        self.document = Document.objects.create(
            submission=self.submission,
            title="Test Document"
        )

    def test_document_creation(self):
        self.assertEqual(self.document.title, "Test Document")
        self.assertEqual(self.document.submission, self.submission)
        self.assertEqual(self.document.status, Document.Status.NOT_UPLOADED)

class SubmissionViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='staffuser', password='password', is_staff=True)
        self.client.login(username='staffuser', password='password')
        self.submission = Submission.objects.create(name="View Test Submission")

    def test_submission_list_view(self):
        response = self.client.get(reverse('submissions:submission_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Test Submission")

    def test_submission_detail_view(self):
        response = self.client.get(reverse('submissions:submission_detail', args=[self.submission.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Test Submission")

    def test_submission_create_view(self):
        response = self.client.post(reverse('submissions:submission_create'), {
            'name': 'New Submission',
            'status': Submission.Status.DRAFT
        })
        # Assuming redirect on success
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(name='New Submission').exists())

    def test_submission_create_view_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('submissions:submission_create'))
        # Should redirect to login
        self.assertEqual(response.status_code, 302)

class DocumentViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='staffuser', password='password', is_staff=True)
        self.client.login(username='staffuser', password='password')
        self.submission = Submission.objects.create(name="Doc View Submission")
        self.document = Document.objects.create(submission=self.submission, title="Old Doc")

    def test_document_create_view(self):
        response = self.client.post(reverse('submissions:document_create', args=[self.submission.pk]), {
            'title': 'New Document',
            'status': Document.Status.NOT_UPLOADED
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(title='New Document').exists())

    def test_document_delete_view(self):
        response = self.client.post(reverse('submissions:document_delete', args=[self.document.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=self.document.pk).exists())
