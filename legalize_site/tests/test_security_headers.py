from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from legalize_site.security import ContentSecurityPolicyMiddleware


class ContentSecurityPolicyMiddlewareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'; object-src 'none'",
        LEGALIZE_CSP_REPORT_ONLY=False,
    )
    def test_sets_content_security_policy_header(self):
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self.factory.get("/"))

        self.assertEqual(
            response["Content-Security-Policy"],
            "default-src 'self'; object-src 'none'",
        )

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'",
        LEGALIZE_CSP_REPORT_ONLY=True,
    )
    def test_sets_report_only_header_when_enabled(self):
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy-Report-Only"], "default-src 'self'")
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'",
        LEGALIZE_CSP_REPORT_ONLY="False",
    )
    def test_string_false_uses_enforcing_header(self):
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy"], "default-src 'self'")
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="",
        LEGALIZE_CSP_REPORT_ONLY=False,
    )
    def test_does_not_overwrite_existing_header(self):
        def get_response(request):
            response = HttpResponse("ok")
            response["Content-Security-Policy"] = "default-src 'none'"
            return response

        middleware = ContentSecurityPolicyMiddleware(get_response)

        response = middleware(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy"], "default-src 'none'")
