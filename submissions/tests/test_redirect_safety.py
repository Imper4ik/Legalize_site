from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from submissions.models import Submission


class SubmissionRedirectSafetyTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.staff = user_model.objects.create_user(username="staff_redirect", password="pass", is_staff=True)
        self.client.login(username="staff_redirect", password="pass")

    def test_quick_create_ignores_external_referer(self):
        response = self.client.post(
            reverse("submissions:submission_quick_create"),
            data={"name": "Safe Redirect", "status": Submission.Status.DRAFT},
            HTTP_REFERER="https://evil.example/steal",
            HTTP_HOST="testserver",
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.url.startswith("https://evil.example"))

    def test_quick_update_ignores_external_referer(self):
        submission = Submission.objects.create(name="Before")

        response = self.client.post(
            reverse("submissions:submission_quick_update", kwargs={"submission_id": submission.pk}),
            data={"name": "After", "status": Submission.Status.DRAFT},
            HTTP_REFERER="https://evil.example/steal",
            HTTP_HOST="testserver",
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.url.startswith("https://evil.example"))

    def test_quick_delete_ignores_external_referer(self):
        submission = Submission.objects.create(name="Delete-safe")

        response = self.client.post(
            reverse("submissions:submission_quick_delete", kwargs={"submission_id": submission.pk}),
            data={},
            HTTP_REFERER="https://evil.example/steal",
            HTTP_HOST="testserver",
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.url.startswith("https://evil.example"))
