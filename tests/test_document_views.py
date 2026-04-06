"""Tests for document views: add, delete, toggle verification, verify all, client_status_api, partials."""
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

from clients.models import Client, Document

User = get_user_model()


class DocumentViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")
        self.test_client = Client.objects.create(
            first_name="Jan", last_name="Kowalski", citizenship="Poland",
            phone="123456789", email="jan_doc@test.com", application_purpose="work",
        )

    def _create_test_document(self, doc_type="passport"):
        return Document.objects.create(
            client=self.test_client,
            document_type=doc_type,
            file=SimpleUploadedFile("test.txt", b"test content", content_type="text/plain"),
        )

    def test_document_delete_post(self):
        doc = self._create_test_document()
        url = reverse("clients:document_delete", kwargs={"pk": doc.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())

    def test_document_delete_get_warns(self):
        doc = self._create_test_document()
        url = reverse("clients:document_delete", kwargs={"pk": doc.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        # Document should NOT be deleted via GET
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())

    def test_toggle_document_verification(self):
        doc = self._create_test_document()
        self.assertFalse(doc.verified)
        url = reverse("clients:toggle_document_verification", kwargs={"doc_id": doc.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        doc.refresh_from_db()
        self.assertTrue(doc.verified)

    def test_toggle_document_verification_ajax(self):
        doc = self._create_test_document()
        url = reverse("clients:toggle_document_verification", kwargs={"doc_id": doc.pk})
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["verified"])

    def test_verify_all_documents(self):
        self._create_test_document("passport")
        self._create_test_document("photos")
        url = reverse("clients:verify_all_documents", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Document.objects.filter(client=self.test_client, verified=True).count(), 2)

    def test_verify_all_documents_ajax(self):
        self._create_test_document()
        url = reverse("clients:verify_all_documents", kwargs={"client_id": self.test_client.pk})
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["verified_count"], 1)

    def test_client_status_api(self):
        url = reverse("clients:client_status_api", kwargs={"pk": self.test_client.pk})
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("checklist_html", data)

    def test_client_overview_partial(self):
        url = reverse("clients:client_overview_partial", kwargs={"pk": self.test_client.pk})
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("html", data)

    def test_client_checklist_partial(self):
        url = reverse("clients:client_checklist_partial", kwargs={"pk": self.test_client.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_update_client_notes_post(self):
        url = reverse("clients:update_client_notes", kwargs={"pk": self.test_client.pk})
        resp = self.client.post(url, {"notes": "New notes here"})
        self.assertEqual(resp.status_code, 302)
        self.test_client.refresh_from_db()
        self.assertEqual(self.test_client.notes, "New notes here")

    def test_update_client_notes_ajax(self):
        url = reverse("clients:update_client_notes", kwargs={"pk": self.test_client.pk})
        resp = self.client.post(
            url, {"notes": "Ajax notes"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
