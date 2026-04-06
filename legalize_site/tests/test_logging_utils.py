import logging

from django.test import SimpleTestCase

from legalize_site.utils.logging import RedactPIIFilter


class RedactPIIFilterTests(SimpleTestCase):
    def test_redacts_passport_and_case_number(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="passport_num=AB123 case_number=XYZ-10",
            args=(),
            exc_info=None,
        )

        allowed = RedactPIIFilter().filter(record)

        self.assertTrue(allowed)
        self.assertIn("passport_num=[REDACTED]", record.msg)
        self.assertIn("case_number=[REDACTED]", record.msg)

    def test_leaves_message_untouched_without_pii(self):
        message = "status=ok user=admin"
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg=message,
            args=(),
            exc_info=None,
        )

        RedactPIIFilter().filter(record)

        self.assertEqual(record.msg, message)
