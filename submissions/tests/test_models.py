from django.test import TestCase
from submissions.models import Submission, Document

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
