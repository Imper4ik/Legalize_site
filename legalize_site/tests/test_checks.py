from django.core.checks import run_checks
from django.test import SimpleTestCase, override_settings


class EmailConfigurationCheckTests(SimpleTestCase):
    def test_skip_when_not_using_supported_backend(self):
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertEqual(run_checks(tags=["legalize_site"]), [])

    def test_error_when_api_backend_missing_key(self):
        for backend, anymail_key in (
            ("anymail.backends.sendgrid.EmailBackend", "SENDGRID_API_KEY"),
            ("anymail.backends.brevo.EmailBackend", "BREVO_API_KEY"),
        ):
            with self.subTest(backend=backend), override_settings(
                EMAIL_BACKEND=backend,
                ANYMAIL={anymail_key: ""},
                DEFAULT_FROM_EMAIL="notifications@example.com",
            ):
                messages = run_checks(tags=["legalize_site"])

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].id, "legalize_site.E001")

    def test_error_when_smtp_backend_missing_key(self):
        cases = [
            {"EMAIL_HOST": "smtp.sendgrid.net"},
            {"EMAIL_HOST": "smtp-relay.brevo.com"},
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides), override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST_PASSWORD="",
                DEFAULT_FROM_EMAIL="notifications@example.com",
                **overrides,
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
                "EMAIL_BACKEND": "anymail.backends.brevo.EmailBackend",
                "ANYMAIL": {"BREVO_API_KEY": "key"},
            },
            {
                "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                "EMAIL_HOST_PASSWORD": "secret",
            },
            {
                "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
                "EMAIL_HOST_PASSWORD": "secret",
                "EMAIL_HOST": "smtp-relay.brevo.com",
            },
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides), override_settings(
                DEFAULT_FROM_EMAIL="no-reply@yourdomain.tld", **overrides
            ):
                messages = run_checks(tags=["legalize_site"])

            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].id, "legalize_site.W001")
