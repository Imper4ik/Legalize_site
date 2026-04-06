"""Tests for client CRUD views and metrics dashboard."""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client as DjangoClient
from django.urls import reverse

from clients.models import Client

User = get_user_model()


class ClientCRUDViewsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")

    def test_client_list_renders(self):
        Client.objects.create(
            first_name="Jan", last_name="Test", citizenship="PL",
            phone="111", email="clist@test.com", application_purpose="work",
        )
        url = reverse("clients:client_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Jan")

    def test_client_list_search(self):
        Client.objects.create(
            first_name="Unique", last_name="Name", citizenship="PL",
            phone="222", email="search@test.com", application_purpose="work",
        )
        url = reverse("clients:client_list")
        resp = self.client.get(url, {"q": "Unique"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Unique")

    def test_client_create_form_renders(self):
        url = reverse("clients:client_add")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_client_create_post(self):
        url = reverse("clients:client_add")
        resp = self.client.post(url, {
            "first_name": "New",
            "last_name": "Client",
            "citizenship": "UA",
            "phone": "333",
            "email": "new@test.com",
            "application_purpose": "study",
            "language": "pl",
            "status": "new",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Client.objects.filter(email="new@test.com").exists())

    def test_client_detail_renders(self):
        client_obj = Client.objects.create(
            first_name="Detail", last_name="Test", citizenship="PL",
            phone="444", email="detail@test.com", application_purpose="work",
        )
        url = reverse("clients:client_detail", kwargs={"pk": client_obj.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Detail")

    def test_client_edit_form_renders(self):
        client_obj = Client.objects.create(
            first_name="Edit", last_name="Test", citizenship="PL",
            phone="555", email="edit@test.com", application_purpose="work",
        )
        url = reverse("clients:client_edit", kwargs={"pk": client_obj.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_client_edit_post(self):
        client_obj = Client.objects.create(
            first_name="Before", last_name="Edit", citizenship="PL",
            phone="666", email="editpost@test.com", application_purpose="work",
        )
        url = reverse("clients:client_edit", kwargs={"pk": client_obj.pk})
        resp = self.client.post(url, {
            "first_name": "After",
            "last_name": "Edit",
            "citizenship": "PL",
            "phone": "666",
            "email": "editpost@test.com",
            "application_purpose": "work",
            "language": "pl",
            "status": "new",
        })
        self.assertEqual(resp.status_code, 302)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.first_name, "After")

    def test_client_delete(self):
        client_obj = Client.objects.create(
            first_name="Delete", last_name="Me", citizenship="PL",
            phone="777", email="del@test.com", application_purpose="work",
        )
        url = reverse("clients:client_delete", kwargs={"pk": client_obj.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Client.objects.filter(pk=client_obj.pk).exists())

    def test_client_print_renders(self):
        client_obj = Client.objects.create(
            first_name="Print", last_name="Test", citizenship="PL",
            phone="888", email="print@test.com", application_purpose="work",
        )
        url = reverse("clients:client_print", kwargs={"pk": client_obj.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_client_wsc_print_renders(self):
        client_obj = Client.objects.create(
            first_name="WSC", last_name="Test", citizenship="PL",
            phone="999", email="wsc@test.com", application_purpose="work",
        )
        url = reverse("clients:client_print_wsc", kwargs={"pk": client_obj.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


class MetricsDashboardTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )

    def setUp(self):
        self.client = DjangoClient()
        self.client.login(username="staff", password="testpass123")

    def test_dashboard_renders(self):
        url = reverse("clients:metrics_dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_context_has_funnel(self):
        url = reverse("clients:metrics_dashboard")
        resp = self.client.get(url)
        self.assertIn("funnel", resp.context)
        funnel = resp.context["funnel"]
        self.assertIn("clients_created", funnel)
        self.assertIn("clients_with_docs", funnel)
        self.assertIn("clients_paid", funnel)

    def test_dashboard_with_data(self):
        Client.objects.create(
            first_name="M", last_name="Test", citizenship="PL",
            phone="111", email="metrics@test.com", application_purpose="work",
        )
        url = reverse("clients:metrics_dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.context["funnel"]["clients_created"], 1)
