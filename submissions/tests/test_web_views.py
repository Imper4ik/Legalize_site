from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from submissions.models import Document, Submission


class SubmissionWebViewsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(username="staff", password="pass", is_staff=True)
        self.non_staff = user_model.objects.create_user(username="user", password="pass", is_staff=False)

    def test_submission_create_view_get_for_staff(self):
        self.client.login(username="staff", password="pass")

        response = self.client.get(reverse("submissions:submission_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "name")

    def test_submission_quick_create_requires_post(self):
        self.client.login(username="staff", password="pass")

        response = self.client.get(reverse("submissions:submission_quick_create"))

        self.assertEqual(response.status_code, 405)

    def test_submission_quick_create_creates_record(self):
        self.client.login(username="staff", password="pass")

        response = self.client.post(
            reverse("submissions:submission_quick_create"),
            data={"name": "Blue Card", "status": Submission.Status.DRAFT},
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Submission.objects.filter(name="Blue Card").exists())

    def test_submission_quick_update_updates_existing(self):
        self.client.login(username="staff", password="pass")
        submission = Submission.objects.create(name="Old name")

        response = self.client.post(
            reverse("submissions:submission_quick_update", kwargs={"submission_id": submission.pk}),
            data={"name": "New name", "status": Submission.Status.IN_PROGRESS},
        )

        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.name, "New name")
        self.assertEqual(submission.status, Submission.Status.IN_PROGRESS)

    def test_submission_quick_delete_removes_record(self):
        self.client.login(username="staff", password="pass")
        submission = Submission.objects.create(name="Delete this")

        response = self.client.post(
            reverse("submissions:submission_quick_delete", kwargs={"submission_id": submission.pk}),
            data={},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(pk=submission.pk).exists())

    def test_document_create_post_invalid_uploaded_without_file(self):
        self.client.login(username="staff", password="pass")
        submission = Submission.objects.create(name="With docs")

        response = self.client.post(
            reverse("submissions:document_create", kwargs={"submission_id": submission.pk}),
            data={"title": "Residence Card", "status": Document.Status.UPLOADED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Document.objects.filter(submission=submission, title="Residence Card").exists())

    def test_non_staff_forbidden_from_staff_views(self):
        self.client.login(username="user", password="pass")

        response = self.client.get(reverse("submissions:submission_create"))

        self.assertEqual(response.status_code, 403)
