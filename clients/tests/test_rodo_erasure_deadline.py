"""RODO art. 12(3): a pending erasure request (art. 17) must be answered within
one month. Staff health alerts / automatic checks surface that statutory clock so
the deadline is not silently breached.
"""
from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from django.utils.translation import override

from clients.testing.factories import create_test_client

ERASURE_ALERT_TITLES = {
    "RODO: срок ответа на запрос об удалении истёк",
    "RODO: приближается срок ответа на запрос об удалении",
}


def _minus_days(days: int):
    return timezone.now() - timezone.timedelta(days=days)


class ErasureDeadlineHealthTests(TestCase):
    def setUp(self) -> None:
        self.client_obj = create_test_client(first_name="Eras", last_name="Sure")

    def _alert_titles(self) -> set[str]:
        with override("ru"):
            return {str(a["title"]) for a in self.client_obj.get_health_alerts()}

    def _erasure_check(self):
        with override("ru"):
            for check in self.client_obj.get_automatic_checks():
                if str(check["label"]) == "RODO: запрос на удаление":
                    return check
        return None

    def test_no_request_shows_nothing(self) -> None:
        self.assertFalse(self._alert_titles() & ERASURE_ALERT_TITLES)
        self.assertIsNone(self._erasure_check())

    def test_fresh_request_is_in_progress_without_alert(self) -> None:
        self.client_obj.erasure_requested_at = _minus_days(2)
        self.client_obj.save(update_fields=["erasure_requested_at"])

        self.assertFalse(self._alert_titles() & ERASURE_ALERT_TITLES)
        check = self._erasure_check()
        self.assertIsNotNone(check)
        self.assertEqual(check["status"], "success")

    def test_approaching_deadline_warns(self) -> None:
        # 26 days elapsed → 4 days left, inside the 7-day warning lead.
        self.client_obj.erasure_requested_at = _minus_days(26)
        self.client_obj.save(update_fields=["erasure_requested_at"])

        self.assertIn(
            "RODO: приближается срок ответа на запрос об удалении",
            self._alert_titles(),
        )
        check = self._erasure_check()
        self.assertIsNotNone(check)
        self.assertEqual(check["status"], "warning")

    def test_breached_deadline_is_danger(self) -> None:
        self.client_obj.erasure_requested_at = _minus_days(40)
        self.client_obj.save(update_fields=["erasure_requested_at"])

        self.assertIn(
            "RODO: срок ответа на запрос об удалении истёк",
            self._alert_titles(),
        )
        check = self._erasure_check()
        self.assertIsNotNone(check)
        self.assertEqual(check["status"], "danger")

    def test_fulfilled_request_clears(self) -> None:
        self.client_obj.erasure_requested_at = _minus_days(40)
        self.client_obj.erasure_fulfilled_at = timezone.now()
        self.client_obj.save(update_fields=["erasure_requested_at", "erasure_fulfilled_at"])

        self.assertFalse(self._alert_titles() & ERASURE_ALERT_TITLES)
        self.assertIsNone(self._erasure_check())
