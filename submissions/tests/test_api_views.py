from __future__ import annotations

import json
from pathlib import Path
import shutil

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from clients.tests.factories import create_staff_user
from submissions.models import Document, Submission


TEST_MEDIA_ROOT = Path(__file__).resolve().parents[2] / "generated_media_test" / "submissions_api"
TEST_MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class SubmissionApiViewsTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.staff = create_staff_user(email="staff@example.com")
        self.client.login(email="staff@example.com", password="pass")

    def test_submission_api_get_returns_items(self):
        Submission.objects.create(name="Work permit")

        response = self.client.get(reverse("submissions:api_submission_list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["status"] == "success")
        self.assertGreaterEqual(len(payload["items"]), 1)
        self.assertIn("Work permit", [item["name"] for item in payload["items"]])

    def test_submission_api_post_creates_submission(self):
        response = self.client.post(
            reverse("submissions:api_submission_list"),
            data=json.dumps({"name": "Blue Card", "status": Submission.Status.DRAFT}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Submission.objects.filter(name="Blue Card").exists())

    def test_submission_api_post_invalid_returns_400(self):
        response = self.client.post(
            reverse("submissions:api_submission_list"),
            data=json.dumps({"name": "   ", "status": Submission.Status.DRAFT}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_submission_detail_delete_removes_submission(self):
        submission = Submission.objects.create(name="Delete me")

        response = self.client.delete(
            reverse("submissions:api_submission_detail", kwargs={"pk": submission.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.filter(pk=submission.pk).exists())
        self.assertTrue(Submission.all_objects.filter(pk=submission.pk, archived_at__isnull=False).exists())

    def test_document_api_post_creates_document(self):
        submission = Submission.objects.create(name="Has docs")

        response = self.client.post(
            reverse("submissions:api_document_list", kwargs={"submission_id": submission.pk}),
            data={"title": "Passport", "status": Document.Status.NOT_UPLOADED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Document.objects.filter(submission=submission, title="Passport").exists())

    def test_document_api_post_requires_file_for_uploaded_status(self):
        submission = Submission.objects.create(name="No file")

        response = self.client.post(
            reverse("submissions:api_document_list", kwargs={"submission_id": submission.pk}),
            data={"title": "Residence card", "status": Document.Status.UPLOADED},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "error")

    def test_submission_detail_api_returns_protected_download_url(self):
        submission = Submission.objects.create(name="Has docs")
        document = Document.objects.create(
            submission=submission,
            title="Passport",
            status=Document.Status.UPLOADED,
            file_path=SimpleUploadedFile("passport.pdf", b"pdf-data", content_type="application/pdf"),
        )

        response = self.client.get(
            reverse("submissions:api_submission_detail", kwargs={"pk": submission.pk})
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["submission"]["documents"][0]["file_path"],
            reverse("submissions:document_download", kwargs={"pk": document.pk}),
        )
