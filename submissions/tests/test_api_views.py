from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from submissions.models import Document, Submission


class SubmissionApiViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(
            username="staff", password="pass", is_staff=True
        )
        self.client.login(username="staff", password="pass")

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
