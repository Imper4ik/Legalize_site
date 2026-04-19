from django.test import SimpleTestCase

from legalize_site.settings.base import _sentry_before_send


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
