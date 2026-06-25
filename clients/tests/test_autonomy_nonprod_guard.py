from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from clients.models import Client, EmailLog
from clients.services.notifications import _send_email


class NonProductionEmailGuardTests(TestCase):
    """The autonomous reminder loop must never dispatch real email to seeded
    Demo/Test Center records, but should still log the attempt."""

    def _make_client(self, **flags: bool) -> Client:
        return Client.objects.create(
            first_name="Guard",
            last_name="Tester",
            citizenship="PL",
            email="guard-tester@example.test",
            **flags,
        )

    @patch("clients.services.notifications._send_mail_with_retry", return_value=1)
    def test_demo_client_email_is_skipped_not_sent(self, mock_send):
        client = self._make_client(is_demo_data=True)

        sent = _send_email(
            "Subject", "Body", [client.email], client=client, template_type="missing_documents"
        )

        self.assertEqual(sent, 0)
        mock_send.assert_not_called()
        log = EmailLog.objects.get(client=client)
        self.assertEqual(log.delivery_status, EmailLog.DELIVERY_STATUS_SKIPPED)
        self.assertTrue(log.is_demo_data)

    @patch("clients.services.notifications._send_mail_with_retry", return_value=1)
    def test_test_client_email_is_skipped_not_sent(self, mock_send):
        client = self._make_client(is_test_data=True)

        sent = _send_email("Subject", "Body", [client.email], client=client)

        self.assertEqual(sent, 0)
        mock_send.assert_not_called()

    @patch("clients.services.notifications._send_confirmation_email")
    @patch("clients.services.notifications._send_mail_with_retry", return_value=1)
    def test_production_client_email_is_dispatched(self, mock_send, _mock_confirm):
        client = self._make_client()

        sent = _send_email(
            "Subject", "Body", [client.email], client=client, template_type="missing_documents"
        )

        self.assertEqual(sent, 1)
        mock_send.assert_called_once()

    def test_production_queryset_excludes_demo_and_test(self):
        prod = self._make_client()
        self._make_client(is_demo_data=True)
        self._make_client(is_test_data=True)

        ids = set(Client.objects.production().values_list("pk", flat=True))

        self.assertEqual(ids, {prod.pk})
