from __future__ import annotations

from unittest.mock import patch

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from legalize_site.checks import (
    EMAIL_CONSOLE_WARNING_ID,
    EMAIL_ERROR_ID,
    EMAIL_WARNING_ID,
    FERNET_KEYS_ERROR_ID,
    RUNTIME_DEPENDENCY_WARNING_ID,
    SECRET_KEY_ERROR_ID,
    encryption_configuration_check,
    email_configuration_check,
    runtime_dependency_check,
)


class EmailConfigurationCheckTests(SimpleTestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@yourdomain.tld",
    )
    def test_console_backend_returns_two_warnings_with_placeholder_domain(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 2)
        self.assertTrue(all(isinstance(msg, Warning) for msg in messages))
        self.assertEqual({m.id for m in messages}, {EMAIL_CONSOLE_WARNING_ID, EMAIL_WARNING_ID})

    @override_settings(
        EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
        ANYMAIL={},
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_sendgrid_without_api_key_returns_error(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, EMAIL_ERROR_ID)

    @override_settings(
        EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
        ANYMAIL={"SENDGRID_API_KEY": "test-key"},
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_sendgrid_with_api_key_has_no_messages(self):
        messages = email_configuration_check()
        self.assertEqual(messages, [])

    @override_settings(
        EMAIL_BACKEND="legalize_site.mail.SafeSMTPEmailBackend",
        EMAIL_HOST="smtp.sendgrid.net",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_smtp_without_password_returns_error(self):
        messages = email_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, EMAIL_ERROR_ID)

    @override_settings(
        EMAIL_BACKEND="legalize_site.mail.SafeSMTPEmailBackend",
        EMAIL_HOST="smtp.sendgrid.net",
        EMAIL_HOST_PASSWORD="secret",
        DEFAULT_FROM_EMAIL="noreply@example.com",
    )
    def test_smtp_with_password_has_no_messages(self):
        messages = email_configuration_check()
        self.assertEqual(messages, [])

    @override_settings(
        IS_PRODUCTION=True,
        SECRET_KEY="django-insecure-change-me",
        FERNET_KEYS=["configured-key"],
        FERNET_KEYS_CONFIGURED=True,
    )
    def test_production_requires_non_placeholder_secret_key(self):
        messages = encryption_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, SECRET_KEY_ERROR_ID)

    @override_settings(
        IS_PRODUCTION=True,
        SECRET_KEY="super-secret",
        FERNET_KEYS=["derived-fallback"],
        FERNET_KEYS_CONFIGURED=False,
    )
    def test_production_requires_explicit_fernet_keys(self):
        messages = encryption_configuration_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Error)
        self.assertEqual(messages[0].id, FERNET_KEYS_ERROR_ID)


class RuntimeDependencyCheckTests(SimpleTestCase):
    @patch("legalize_site.checks.collect_runtime_dependency_statuses")
    def test_runtime_dependency_check_warns_about_missing_dependencies(self, collect_mock):
        collect_mock.return_value = [
            {
                "label": "pdf2image",
                "required_for": "OCR on PDF scans",
                "hint": "Install pdf2image.",
                "available": False,
            },
            {
                "label": "tesseract",
                "required_for": "OCR text extraction",
                "hint": "Install tesseract.",
                "available": True,
            },
        ]

        messages = runtime_dependency_check()

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], Warning)
        self.assertEqual(messages[0].id, RUNTIME_DEPENDENCY_WARNING_ID)
        self.assertIn("pdf2image", messages[0].msg)

    @patch("legalize_site.checks.collect_runtime_dependency_statuses", return_value=[])
    def test_runtime_dependency_check_returns_no_messages_when_all_available(self, _collect_mock):
        self.assertEqual(runtime_dependency_check(), [])
