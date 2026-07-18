from django.test import RequestFactory, SimpleTestCase, override_settings

from legalize_site.context_processors import support_contact


class SupportContactContextProcessorTests(SimpleTestCase):
    @override_settings(DEFAULT_FROM_EMAIL="helpdesk@example.test")
    def test_uses_configured_default_from_address(self) -> None:
        request = RequestFactory().get("/")

        self.assertEqual(support_contact(request), {"support_email": "helpdesk@example.test"})
