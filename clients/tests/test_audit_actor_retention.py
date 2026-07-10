"""Audit history must survive employee removal and still say who acted.

ClientActivity.actor is SET_NULL so the row is never cascade-deleted, and an
immutable actor_label snapshot preserves the actor identity even after the
employee account is deleted or deactivated.
"""
from __future__ import annotations

from django.test import TestCase

from clients.models import ClientActivity, StaffAuditEvent
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


class StaffAuditEventRetentionTests(TestCase):
    def setUp(self) -> None:
        self.actor = create_test_user(role="Admin", email="admin-actor@example.test")
        self.target = create_test_user(role="Staff", email="staff-target@example.test")
        self.target.first_name = "Tomasz"
        self.target.last_name = "Target"
        self.target.save(update_fields=["first_name", "last_name"])

    def _event(self) -> StaffAuditEvent:
        return StaffAuditEvent.objects.create(
            actor=self.actor,
            target=self.target,
            event_type=StaffAuditEvent.EVENT_STAFF_UPDATED,
            summary="Staff user updated",
        )

    def test_labels_snapshotted_on_create(self) -> None:
        event = self._event()
        self.assertIn("staff-target@example.test", event.target_label)
        self.assertIn("Tomasz Target", event.target_label)
        self.assertIn("admin-actor@example.test", event.actor_label)

    def test_event_survives_target_deletion(self) -> None:
        event = self._event()
        event_id = event.pk
        target_label = event.target_label

        # The whole point of LS-010: deleting the targeted employee must not
        # cascade-delete the audit event about them.
        self.target.delete()

        self.assertTrue(StaffAuditEvent.objects.filter(pk=event_id).exists())
        event.refresh_from_db()
        self.assertIsNone(event.target)
        self.assertEqual(event.target_label, target_label)
        self.assertIn("staff-target@example.test", event.target_display)

    def test_event_survives_actor_deletion(self) -> None:
        event = self._event()
        self.actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor)
        self.assertIn("admin-actor@example.test", event.actor_display)

    def test_labels_are_write_once(self) -> None:
        event = self._event()
        original = event.target_label
        other = create_test_user(role="Staff", email="other@example.test")
        event.target = other
        event.save()
        event.refresh_from_db()
        # Re-pointing the FK does not rewrite the historical snapshot.
        self.assertEqual(event.target_label, original)
