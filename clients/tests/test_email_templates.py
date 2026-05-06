from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class EmailTemplatesTests(SimpleTestCase):
    def setUp(self):
        self.email_dir = Path(settings.BASE_DIR) / "clients" / "templates" / "clients" / "email"
        self.languages = ["en", "pl", "ru", ""]
        self.template_types = [
            "appointment_notification",
            "expired_documents",
            "expiring_documents",
            "missing_documents",
            "required_documents",
        ]

    def test_all_notification_templates_exist_for_all_languages(self):
        missing = []
        for template_type in self.template_types:
            for lang in self.languages:
                path = self.email_dir / lang / f"{template_type}.txt" if lang else self.email_dir / f"{template_type}.txt"
                if not path.exists():
                    missing.append(str(path))

        self.assertEqual(missing, [], "Missing email templates found")

    def test_expired_documents_uses_display_name(self):
        for lang in self.languages:
            path = self.email_dir / lang / "expired_documents.txt" if lang else self.email_dir / "expired_documents.txt"
            if path.exists():
                content = path.read_text(encoding="utf-8")
                self.assertIn("document.display_name", content)
                self.assertNotIn("document.get_document_type_display", content)
