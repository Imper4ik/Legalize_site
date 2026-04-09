from __future__ import annotations

from unittest.mock import patch

from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from legalize_site.mail import SafeSMTPEmailBackend


class SafeSMTPEmailBackendTests(SimpleTestCase):
    def test_send_messages_returns_zero_for_empty_input(self):
        backend = SafeSMTPEmailBackend()
        self.assertEqual(backend.send_messages([]), 0)

    @override_settings(EMAIL_FALLBACK_TO_CONSOLE=True)
    @patch("django.core.mail.backends.smtp.EmailBackend.send_messages", side_effect=RuntimeError("smtp down"))
    @patch("django.core.mail.backends.console.EmailBackend.send_messages", return_value=1)
    def test_falls_back_to_console_backend_on_smtp_error_when_enabled(self, console_send, _smtp_send):
        backend = SafeSMTPEmailBackend()
        result = backend.send_messages([EmailMessage("Subj", "Body", "from@example.com", ["to@example.com"])])

        self.assertEqual(result, 1)
        console_send.assert_called_once()

    @override_settings(EMAIL_FALLBACK_TO_CONSOLE=False)
    @patch("django.core.mail.backends.smtp.EmailBackend.send_messages", side_effect=RuntimeError("smtp down"))
    def test_raises_smtp_error_when_console_fallback_disabled(self, _smtp_send):
        backend = SafeSMTPEmailBackend()

        with self.assertRaises(RuntimeError):
            backend.send_messages([EmailMessage("Subj", "Body", "from@example.com", ["to@example.com"])])
