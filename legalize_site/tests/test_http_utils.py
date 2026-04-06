from django.test import RequestFactory, SimpleTestCase

from legalize_site.utils.http import request_is_ajax


class RequestIsAjaxTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_detects_xmlhttprequest_header(self):
        request = self.factory.get("/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertTrue(request_is_ajax(request))

    def test_detects_json_accept_header(self):
        request = self.factory.get("/", HTTP_ACCEPT="application/json")
        self.assertTrue(request_is_ajax(request))

    def test_detects_cors_for_non_get(self):
        request = self.factory.post("/", HTTP_SEC_FETCH_MODE="cors")
        self.assertTrue(request_is_ajax(request))

    def test_does_not_treat_regular_get_as_ajax(self):
        request = self.factory.get("/")
        self.assertFalse(request_is_ajax(request))
