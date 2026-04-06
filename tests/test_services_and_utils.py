"""Tests for services: pricing, responses, http utility, logging filter."""
from django.http import HttpRequest
from django.test import TestCase, SimpleTestCase

from clients.services.pricing import get_service_price, SERVICE_PRICES
from clients.services.responses import ResponseHelper, apply_no_store, json_no_store
from legalize_site.utils.http import request_is_ajax
from legalize_site.utils.logging import RedactPIIFilter

import logging


class PricingServiceTest(TestCase):
    def test_known_service_returns_price(self):
        price = get_service_price("work_service")
        self.assertGreater(price, 0)

    def test_unknown_service_returns_zero(self):
        price = get_service_price("nonexistent_service")
        self.assertEqual(price, 0.0)

    def test_all_default_prices_exist(self):
        for code, expected_price in SERVICE_PRICES.items():
            price = get_service_price(code)
            self.assertGreater(price, 0, f"Price for {code} should be > 0")


class ResponseHelperTest(SimpleTestCase):
    def _make_request(self, **headers):
        request = HttpRequest()
        request.method = "GET"
        for key, val in headers.items():
            request.META[key] = val
        return request

    def test_success_response(self):
        request = self._make_request(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        helper = ResponseHelper(request)
        resp = helper.success(message="OK", extra_data="test")
        self.assertEqual(resp.status_code, 200)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"], "OK")
        self.assertEqual(data["extra_data"], "test")

    def test_error_response(self):
        request = self._make_request()
        helper = ResponseHelper(request)
        resp = helper.error(message="Bad", status=400, errors={"field": ["Error"]})
        self.assertEqual(resp.status_code, 400)
        import json
        data = json.loads(resp.content)
        self.assertEqual(data["status"], "error")
        self.assertIn("errors", data)

    def test_forbidden_response(self):
        request = self._make_request()
        helper = ResponseHelper(request)
        resp = helper.forbidden()
        self.assertEqual(resp.status_code, 403)

    def test_expects_json_with_ajax_header(self):
        request = self._make_request(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(ResponseHelper(request).expects_json)

    def test_expects_json_with_accept_json(self):
        request = self._make_request(HTTP_ACCEPT="application/json")
        self.assertTrue(ResponseHelper(request).expects_json)

    def test_not_expects_json_for_normal_request(self):
        request = self._make_request()
        self.assertFalse(ResponseHelper(request).expects_json)


class ApplyNoStoreTest(SimpleTestCase):
    def test_adds_cache_control_header(self):
        from django.http import HttpResponse
        response = HttpResponse("test")
        result = apply_no_store(response)
        self.assertEqual(result["Cache-Control"], "no-store")

    def test_json_no_store_adds_header(self):
        resp = json_no_store({"key": "value"})
        self.assertEqual(resp["Cache-Control"], "no-store")
        self.assertEqual(resp.status_code, 200)


class RequestIsAjaxTest(SimpleTestCase):
    def _make_request(self, **meta):
        req = HttpRequest()
        req.method = "GET"
        for k, v in meta.items():
            req.META[k] = v
        return req

    def test_xmlhttprequest_header(self):
        req = self._make_request(HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(request_is_ajax(req))

    def test_accept_json_header(self):
        req = self._make_request(HTTP_ACCEPT="application/json")
        self.assertTrue(request_is_ajax(req))

    def test_cors_post_detected(self):
        req = self._make_request(HTTP_SEC_FETCH_MODE="cors")
        req.method = "POST"
        self.assertTrue(request_is_ajax(req))

    def test_normal_request(self):
        req = self._make_request()
        self.assertFalse(request_is_ajax(req))


class RedactPIIFilterTest(SimpleTestCase):
    def test_redacts_passport_num(self):
        f = RedactPIIFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "passport_num=ABC123456", (), None
        )
        f.filter(record)
        self.assertIn("[REDACTED]", record.msg)
        self.assertNotIn("ABC123456", record.msg)

    def test_redacts_case_number(self):
        f = RedactPIIFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "case_number=WSC-II-S.123", (), None
        )
        f.filter(record)
        self.assertIn("[REDACTED]", record.msg)
        self.assertNotIn("WSC-II-S.123", record.msg)

    def test_does_not_redact_normal_text(self):
        f = RedactPIIFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "", 0, "Normal log message", (), None
        )
        f.filter(record)
        self.assertEqual(record.msg, "Normal log message")
