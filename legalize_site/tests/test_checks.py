from __future__ import annotations

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from legalize_site.checks import (
    EMAIL_CONSOLE_WARNING_ID,
    EMAIL_ERROR_ID,
    EMAIL_WARNING_ID,
    email_configuration_check,
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
