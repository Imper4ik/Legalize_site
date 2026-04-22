from django.test import SimpleTestCase

from legalize_site.settings.base import _sentry_before_send
from django.core.exceptions import ImproperlyConfigured
from importlib import reload
from unittest.mock import patch
import legalize_site.settings.production as production_settings


class SentryConfigTests(SimpleTestCase):
    def test_before_send_redacts_request_user_and_extra_fields(self):
        event = {
            "request": {
                "method": "POST",
                "data": {"email": "person@example.com"},
                "headers": {"X-Contact": "+48123123123"},
                "query_string": "email=person@example.com",
                "cookies": {"sessionid": "abc"},
            },
            "user": {"email": "person@example.com"},
            "extra": {"passport_num": "AB1234567"},
        }

        scrubbed = _sentry_before_send(event, hint={})

        self.assertEqual(scrubbed["request"]["data"], "[REDACTED]")
        self.assertNotIn("cookies", scrubbed["request"])
        self.assertIn("[REDACTED]", scrubbed["request"]["query_string"])
        self.assertEqual(scrubbed["user"]["email"], "[REDACTED]")
        self.assertEqual(scrubbed["extra"]["passport_num"], "[REDACTED]")

    def test_production_settings_raise_when_debug_enabled(self):
        with patch.dict(
            "os.environ",
            {
                "DJANGO_SETTINGS_MODULE": "legalize_site.settings.production",
                "DEBUG": "True",
                "ALLOWED_HOSTS": "crm.example.com",
                "CSRF_TRUSTED_ORIGINS": "https://crm.example.com",
                "SECRET_KEY": "secret",
                "FERNET_KEYS": "x" * 44,
            },
            clear=False,
        ):
            with self.assertRaises(ImproperlyConfigured):
                reload(production_settings)
