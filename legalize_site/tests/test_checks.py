from django.core.checks import run_checks
from django.test import SimpleTestCase, override_settings


class SendGridConfigurationCheckTests(SimpleTestCase):
    def test_skip_when_not_using_sendgrid_backend(self):
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertEqual(run_checks(tags=["legalize_site"]), [])

    def test_error_when_api_backend_missing_key(self):
        with override_settings(
            EMAIL_BACKEND="anymail.backends.sendgrid.EmailBackend",
            ANYMAIL={},
            DEFAULT_FROM_EMAIL="notifications@example.com",
        ):
            messages = run_checks(tags=["legalize_site"])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, "legalize_site.E001")

    def test_error_when_smtp_backend_missing_key(self):
        with override_settings(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST_PASSWORD="",
            DEFAULT_FROM_EMAIL="notifications@example.com",
        ):
            messages = run_checks(tags=["legalize_site"])

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].id, "legalize_site.E001")

    def test_warning_when_default_from_email_placeholder(self):
        cases = [
            {
                "EMAIL_BACKEND": "anymail.backends.sendgrid.EmailBackend",
                "ANYMAIL": {"SENDGRID_API_KEY": "key"},
            },
            {
                "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                "EMAIL_HOST_PASSWORD": "secret",
            },
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides), override_settings(
                DEFAULT_FROM_EMAIL="no-reply@yourdomain.tld", **overrides
            ):
                messages = run_checks(tags=["legalize_site"])

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].id, "legalize_site.W001")
