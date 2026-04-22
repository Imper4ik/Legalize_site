from __future__ import annotations

import logging

from django.test import TestCase
from django.urls import reverse

from legalize_site.utils.logging import clear_log_context, set_log_context


class ObservabilityTests(TestCase):
    def test_request_id_header_is_added_to_response(self):
        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])

    def test_logging_filter_injects_request_context(self):
        logger = logging.getLogger("legalize_site.tests.observability")
        clear_log_context()
        set_log_context(request_id="req-123", correlation_id="corr-456")
        record = logger.makeRecord(
            name=logger.name,
            level=logging.INFO,
            fn=__file__,
            lno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )

        from legalize_site.utils.logging import RequestContextFilter

        RequestContextFilter().filter(record)
        self.assertEqual(record.request_id, "req-123")
        self.assertEqual(record.correlation_id, "corr-456")
