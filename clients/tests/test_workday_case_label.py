"""Workday alerts carry the case number so a client with several cases is not
mistaken for a duplicate in the queue.
"""
from __future__ import annotations

from datetime import date

from django.test import TestCase

from clients.services.workday import build_workday_context
from clients.testing.factories import create_test_client, create_test_user


class WorkdayCaseLabelTests(TestCase):
    def test_fingerprints_alert_includes_case_number(self) -> None:
        staff = create_test_user(role="Admin")
        client = create_test_client(first_name="Label", last_name="Case")
        case = client.cases.get()
        case.workflow_stage = "waiting_decision"
        case.fingerprints_date = date(2026, 1, 1)
        case.authority_case_number = "WSC-II-P.6151.42.2026"
        case.save(update_fields=["workflow_stage", "fingerprints_date", "authority_case_number"])

        context = build_workday_context(staff, today=date(2026, 6, 1), limit_per_section=10)

        alerts = [
            alert
            for card in context["workday_clients"]
            if card["client"].pk == client.pk
            for alert in card["alerts"]
            if alert["section_key"] == "fingerprints_followup"
        ]
        self.assertTrue(alerts)
        self.assertEqual(alerts[0]["case_label"], "WSC-II-P.6151.42.2026")
