"""Tests for Client model methods: hash, save, get_document_checklist, get_document_name_by_code."""
from django.test import TestCase

from clients.models import Client


class ClientModelTest(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            first_name="Model", last_name="Test", citizenship="PL",
            phone="111", email="model@test.com", application_purpose="work",
        )

    def test_str_representation(self):
        self.assertEqual(str(self.client_obj), "Model Test")

    def test_get_absolute_url(self):
        url = self.client_obj.get_absolute_url()
        self.assertIn(str(self.client_obj.pk), url)

    def test_case_number_hash_saved_on_set(self):
        self.client_obj.case_number = "WSC-II-S.1234.56789.2023"
        self.client_obj.save()
        self.assertIsNotNone(self.client_obj.case_number_hash)

    def test_case_number_hash_cleared_on_empty(self):
        self.client_obj.case_number = "TEST"
        self.client_obj.save()
        self.assertIsNotNone(self.client_obj.case_number_hash)
        self.client_obj.case_number = ""
        self.client_obj.save()
        self.assertIsNone(self.client_obj.case_number_hash)

    def test_hash_case_number_is_deterministic(self):
        h1 = Client.hash_case_number("WSC-II-S.1234")
        h2 = Client.hash_case_number("wsc-ii-s.1234")
        self.assertEqual(h1, h2)

    def test_normalize_case_number(self):
        self.assertEqual(Client.normalize_case_number("  abc def  "), "ABCDEF")

    def test_get_document_checklist_empty(self):
        checklist = self.client_obj.get_document_checklist()
        # Could be empty or populated depending on DocumentRequirement data
        self.assertIsInstance(checklist, list)

    def test_get_document_name_by_code_unknown(self):
        name = self.client_obj.get_document_name_by_code("totally_unknown_type")
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_application_purpose_display(self):
        display = self.client_obj.get_application_purpose_display()
        self.assertIsInstance(display, str)
        self.assertGreater(len(display), 0)

    def test_update_fields_includes_hash(self):
        """When saving with update_fields including case_number, hash is auto-added."""
        self.client_obj.case_number = "NEW-123"
        self.client_obj.save(update_fields=["case_number"])
        self.client_obj.refresh_from_db()
        self.assertIsNotNone(self.client_obj.case_number_hash)
