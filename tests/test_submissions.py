"""Tests for submissions app: views and API endpoints."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

from submissions.models import Submission

User = get_user_model()


class SubmissionViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")

    def test_submission_list_renders(self):
        Submission.objects.create(name="Test Submission", slug="test-sub", status="active")
        url = reverse("submissions:submission_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_submission_create_get(self):
        url = reverse("submissions:submission_create")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_submission_create_post(self):
        url = reverse("submissions:submission_create")
        resp = self.client.post(url, {"name": "New Basis", "slug": "new-basis", "status": "active"})
        self.assertIn(resp.status_code, (200, 302))

    def test_submission_detail_renders(self):
        sub = Submission.objects.create(name="Detail Sub", slug="detail-sub", status="active")
        url = reverse("submissions:submission_detail", kwargs={"pk": sub.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_submission_quick_create(self):
        url = reverse("submissions:submission_quick_create")
        resp = self.client.post(url, {"name": "Quick Sub", "slug": "quick-sub", "status": "active"})
        self.assertEqual(resp.status_code, 302)

    def test_submission_quick_create_get_not_allowed(self):
        url = reverse("submissions:submission_quick_create")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)

    def test_submission_quick_delete(self):
        sub = Submission.objects.create(name="Del Sub", slug="del-sub", status="active")
        url = reverse("submissions:submission_quick_delete", kwargs={"submission_id": sub.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Submission.objects.filter(pk=sub.pk).exists())


class SubmissionAPITest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")

    def test_api_list_submissions(self):
        Submission.objects.create(name="API Sub", slug="api-sub", status="active")
        url = reverse("submissions:api_submission_list")
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_api_create_submission_via_form(self):
        """Test creating submission via POST form data (not JSON)."""
        url = reverse("submissions:api_submission_list")
        resp = self.client.post(
            url,
            {"name": "API Created", "status": "draft"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")

    def test_api_get_submission_detail(self):
        sub = Submission.objects.create(name="API Detail", slug="api-detail", status="active")
        url = reverse("submissions:api_submission_detail", kwargs={"pk": sub.pk})
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")

    def test_api_delete_submission(self):
        sub = Submission.objects.create(name="API Del", slug="api-del", status="active")
        url = reverse("submissions:api_submission_detail", kwargs={"pk": sub.pk})
        resp = self.client.delete(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Submission.objects.filter(pk=sub.pk).exists())
