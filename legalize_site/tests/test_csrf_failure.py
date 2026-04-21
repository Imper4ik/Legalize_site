from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from legalize_site.views import csrf_failure


class CsrfFailureViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_ajax_request_gets_json_error(self):
        request = self.factory.post(
            "/clients/1/payment/1/edit/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        request.user = AnonymousUser()

        response = csrf_failure(request, reason="CSRF token missing")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["status"], "error")
        self.assertIn("message", response.json())
        self.assertEqual(response["Cache-Control"], "no-store, no-cache, must-revalidate")

    def test_browser_request_gets_html_error_page(self):
        request = self.factory.post("/clients/1/payment/1/edit/")
        request.user = AnonymousUser()

        response = csrf_failure(request, reason="CSRF token missing")

        self.assertEqual(response.status_code, 403)
        self.assertIn("text/html", response["Content-Type"])
        self.assertEqual(response["Cache-Control"], "no-store, no-cache, must-revalidate")
