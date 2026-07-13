from __future__ import annotations

from django.test import SimpleTestCase

from clients.services.activity import sanitize_activity_metadata


class ActivityMetadataSanitizerTests(SimpleTestCase):
    def test_preserves_approved_business_metadata(self):
        sanitized = sanitize_activity_metadata(
            {
                "workflow_stage": "documents",
                "status": "in_progress",
                "document_type": "passport",
                "selected_purpose": "work",
                "application_purpose": "work",
                "payment_id": 42,
            }
        )

        self.assertEqual(
            sanitized,
            {
                "workflow_stage": "documents",
                "status": "in_progress",
                "document_type": "passport",
                "selected_purpose": "work",
                "application_purpose": "work",
                "payment_id": "42",
            },
        )

    def test_still_rejects_pii_and_unbounded_values(self):
        sanitized = sanitize_activity_metadata(
            {
                "email": "client@example.com",
                "status": "x" * 101,
                "payment_id": True,
            }
        )

        self.assertEqual(sanitized, {})
