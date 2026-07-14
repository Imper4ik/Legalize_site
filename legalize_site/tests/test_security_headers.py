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
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'; script-src 'self' 'unsafe-inline'",
        LEGALIZE_CSP_REPORT_ONLY=False,
        LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY="default-src 'self'; script-src 'self'",
    )
    def test_strict_report_only_is_sent_alongside_enforced_policy(self):
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        request = self.factory.get("/")
        response = middleware(request)

        # The enforced policy binds the per-request nonce to script-src.
        nonce = request.csp_nonce
        self.assertEqual(
            response["Content-Security-Policy"],
            f"default-src 'self'; script-src 'nonce-{nonce}' 'self' 'unsafe-inline'",
        )
        # ...while the strict policy is reported (not enforced) for inventory.
        self.assertEqual(
            response["Content-Security-Policy-Report-Only"],
            f"default-src 'self'; script-src 'self' 'nonce-{nonce}'",
        )

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'; style-src 'self' 'unsafe-inline'",
        LEGALIZE_CSP_REPORT_ONLY=False,
        LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY="default-src 'self'; style-src 'self'; script-src 'self'",
    )
    def test_strict_report_only_binds_nonce_to_style_src(self):
        # Templates carry <style nonce="{{ request.csp_nonce }}">, so the strict
        # report-only policy must whitelist them the same way it does scripts —
        # leaving only style="..." attributes in the violation telemetry.
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        request = self.factory.get("/")
        response = middleware(request)

        nonce = request.csp_nonce
        self.assertEqual(
            response["Content-Security-Policy-Report-Only"],
            f"default-src 'self'; style-src 'self' 'nonce-{nonce}'; script-src 'self' 'nonce-{nonce}'",
        )

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'; script-src 'self' https://cdn.jsdelivr.net",
        LEGALIZE_CSP_REPORT_ONLY=False,
    )
    def test_script_src_gets_per_request_nonce_without_unsafe_inline(self):
        # Reflects the production policy (no 'unsafe-inline' in script-src): the
        # middleware must add the nonce so nonced inline scripts still run.
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        request = self.factory.get("/")
        response = middleware(request)

        nonce = request.csp_nonce
        self.assertEqual(
            response["Content-Security-Policy"],
            f"default-src 'self'; script-src 'nonce-{nonce}' 'self' https://cdn.jsdelivr.net",
        )
        self.assertNotIn("'unsafe-inline'", response["Content-Security-Policy"])

    @override_settings(
        LEGALIZE_CONTENT_SECURITY_POLICY="default-src 'self'",
        LEGALIZE_CSP_REPORT_ONLY=True,
        LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY="default-src 'self'; script-src 'self'",
    )
    def test_strict_report_only_is_skipped_when_main_policy_is_report_only(self):
        # Avoid emitting two competing Report-Only headers.
        middleware = ContentSecurityPolicyMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self.factory.get("/"))

        self.assertEqual(response["Content-Security-Policy-Report-Only"], "default-src 'self'")
        self.assertNotIn("Content-Security-Policy", response)

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
