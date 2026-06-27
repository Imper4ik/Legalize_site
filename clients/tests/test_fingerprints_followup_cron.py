from __future__ import annotations

from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from clients.models import Client, StaffTask


@override_settings(LANGUAGE_CODE="ru")
class FingerprintsFollowupCronTests(TestCase):
    """The reminder cron must autonomously raise (and clear) a staff task for
    cases stuck in waiting_decision after fingerprints, without anyone opening
    the Workday dashboard."""

    def _stale_client(self, **kwargs) -> Client:
        return Client.objects.create(
            first_name="Stale",
            last_name="Decision",
            workflow_stage="waiting_decision",
            fingerprints_date=timezone.localdate() - timedelta(days=120),
            **kwargs,
        )

    def _run(self) -> None:
        call_command("update_reminders", "--only", "fingerprints-followup")

    def test_creates_task_for_stale_case(self) -> None:
        client = self._stale_client()
        self._run()
        tasks = StaffTask.objects.filter(
            client=client, task_type="fingerprints_followup", status="open"
        )
        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.first().priority, "medium")

    def test_is_idempotent(self) -> None:
        client = self._stale_client()
        self._run()
        self._run()
        self.assertEqual(
            StaffTask.objects.filter(
                client=client,
                task_type="fingerprints_followup",
                status__in=["open", "in_progress"],
            ).count(),
            1,
        )

    def test_no_task_before_threshold(self) -> None:
        client = Client.objects.create(
            first_name="Fresh",
            last_name="Decision",
            workflow_stage="waiting_decision",
            fingerprints_date=timezone.localdate() - timedelta(days=5),
        )
        self._run()
        self.assertFalse(
            StaffTask.objects.filter(client=client, task_type="fingerprints_followup").exists()
        )

    def test_autocloses_when_decision_recorded(self) -> None:
        client = self._stale_client()
        self._run()
        task = StaffTask.objects.get(client=client, task_type="fingerprints_followup")

        case = client.cases.first()
        case.decision_date = timezone.localdate()
        case.save(update_fields=["decision_date"])

        self._run()
        task.refresh_from_db()
        self.assertEqual(task.status, "done")

    def test_skips_archived_client(self) -> None:
        client = self._stale_client()
        client.archived_at = timezone.now()
        client.save(update_fields=["archived_at"])
        self._run()
        self.assertFalse(
            StaffTask.objects.filter(client=client, task_type="fingerprints_followup").exists()
        )
