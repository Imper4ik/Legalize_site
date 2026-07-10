"""Audit history must survive employee removal and still say who acted.

ClientActivity.actor is SET_NULL so the row is never cascade-deleted, and an
immutable actor_label snapshot preserves the actor identity even after the
employee account is deleted or deactivated.
"""
from __future__ import annotations

from django.test import TestCase

from clients.models import ClientActivity
from clients.services.activity import describe_actor, log_client_activity
from clients.testing.factories import create_test_client, create_test_user


class AuditActorRetentionTests(TestCase):
    def setUp(self) -> None:
        self.employee = create_test_user(role="Staff", email="auditor@example.test")
        self.employee.first_name = "Olga"
        self.employee.last_name = "Auditor"
        self.employee.save(update_fields=["first_name", "last_name"])
        self.client_obj = create_test_client(first_name="Sub", last_name="Ject")

    def _log(self) -> ClientActivity:
        return log_client_activity(
            client=self.client_obj,
            actor=self.employee,
            event_type="client_updated",
            summary="Updated client",
        )

    def test_actor_label_snapshot_is_recorded(self) -> None:
        activity = self._log()
        self.assertEqual(activity.actor, self.employee)
        self.assertIn("auditor@example.test", activity.actor_label)
        self.assertIn("Olga Auditor", activity.actor_label)

    def test_event_and_identity_survive_employee_deletion(self) -> None:
        activity = self._log()
        activity_id = activity.pk
        label = activity.actor_label

        # Physically delete the employee account.
        self.employee.delete()

        activity.refresh_from_db()
        # The audit row is not cascade-deleted...
        self.assertTrue(ClientActivity.objects.filter(pk=activity_id).exists())
        # ...the FK is nulled...
        self.assertIsNone(activity.actor)
        # ...but the snapshot still identifies who performed the action.
        self.assertEqual(activity.actor_label, label)
        self.assertIn("auditor@example.test", activity.actor_label)

    def test_deactivation_preserves_actor_and_label(self) -> None:
        activity = self._log()
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])

        activity.refresh_from_db()
        self.assertEqual(activity.actor, self.employee)
        self.assertIn("auditor@example.test", activity.actor_label)

    def test_describe_actor_handles_anonymous_and_none(self) -> None:
        self.assertEqual(describe_actor(None), "")
