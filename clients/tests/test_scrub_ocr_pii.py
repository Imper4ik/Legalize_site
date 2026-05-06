from django.core.management import call_command
from django.test import TestCase
from clients.models import Client, Document
from io import StringIO

class ScrubOcrPiiCommandTests(TestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(
            first_name="Test",
            last_name="User",
            email="test@example.com"
        )
        
        # Document with PII that needs scrubbing
        self.doc_to_scrub = Document.objects.create(
            client=self.client_obj,
            document_type="wezwanie",
            awaiting_confirmation=False,
            parsed_data={
                "full_name": "Test User",
                "case_number": "12345",
                "text": "Some raw text",
                "ticket_number": "X1",
                "fingerprints_date": "2026-01-01"
            }
        )
        
        # Document awaiting confirmation should be ignored
        self.doc_awaiting = Document.objects.create(
            client=self.client_obj,
            document_type="wezwanie",
            awaiting_confirmation=True,
            parsed_data={
                "full_name": "Test User",
                "case_number": "54321",
                "text": "Some raw text"
            }
        )

    def test_scrub_ocr_pii_dry_run(self):
        out = StringIO()
        call_command("scrub_ocr_pii", "--dry-run", stdout=out)
        self.assertIn("DRY RUN: 1 out of 1 documents would be scrubbed", out.getvalue())
        
        # Verify no changes made
        self.doc_to_scrub.refresh_from_db()
        self.assertIn("full_name", self.doc_to_scrub.parsed_data)

    def test_scrub_ocr_pii_normal_run(self):
        out = StringIO()
        call_command("scrub_ocr_pii", stdout=out)
        self.assertIn("Successfully scrubbed PII from 1 out of 1 documents", out.getvalue())
        
        self.doc_to_scrub.refresh_from_db()
        self.assertTrue(self.doc_to_scrub.parsed_data.get("pii_scrubbed"))
        self.assertNotIn("full_name", self.doc_to_scrub.parsed_data)
        self.assertNotIn("case_number", self.doc_to_scrub.parsed_data)
        self.assertNotIn("text", self.doc_to_scrub.parsed_data)
        self.assertIn("ticket_number", self.doc_to_scrub.parsed_data)
        self.assertIn("fingerprints_date", self.doc_to_scrub.parsed_data)
        
        # Verify awaiting doc is untouched
        self.doc_awaiting.refresh_from_db()
        self.assertIn("full_name", self.doc_awaiting.parsed_data)
