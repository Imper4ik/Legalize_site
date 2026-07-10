from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models


class EmployeePermission(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_permission",
    )
    can_manage_payments = models.BooleanField(default=False)
    can_send_custom_email = models.BooleanField(default=False)
    can_send_mass_email = models.BooleanField(default=False)
    can_export_clients = models.BooleanField(default=False)
    can_delete_clients = models.BooleanField(default=False)
    can_delete_documents = models.BooleanField(default=False)
    can_manage_checklists = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)
    can_manage_staff_tasks = models.BooleanField(default=False)
    can_run_ocr_review = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Employee permission"
        verbose_name_plural = "Employee permissions"

    def __str__(self) -> str:
        return f"EmployeePermission(user={self.user_id})"


class StaffAuditEvent(models.Model):
    EVENT_STAFF_UPDATED = "staff_updated"
    EVENT_STAFF_ACTIVE_TOGGLED = "staff_active_toggled"
    EVENT_TEST_CENTER_RUN = "test_center_run"
    EVENT_TEST_CENTER_CLEANUP = "test_center_cleanup"

    EVENT_TYPE_CHOICES = (
        (EVENT_STAFF_UPDATED, "Staff user updated"),
        (EVENT_STAFF_ACTIVE_TOGGLED, "Staff active status toggled"),
        (EVENT_TEST_CENTER_RUN, "Test Center run"),
        (EVENT_TEST_CENTER_CLEANUP, "Test Center cleanup"),
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_audit_events",
    )
    # SET_NULL (not CASCADE): deleting the targeted employee must never erase the
    # audit events about them. Null-safe because target_label keeps the identity.
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_staff_audit_events",
    )
    # Write-once identity snapshots so the event still says who acted on whom
    # after either account is deleted or deactivated.
    actor_label = models.CharField(max_length=255, blank=True, default="")
    target_label = models.CharField(max_length=255, blank=True, default="")
    event_type = models.CharField(max_length=64, choices=EVENT_TYPE_CHOICES)
    summary = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    is_demo_data = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target", "-created_at"], name="staffaudit_target_created_idx"),
            models.Index(fields=["actor", "-created_at"], name="staffaudit_actor_created_idx"),
        ]
        verbose_name = "Staff audit event"
        verbose_name_plural = "Staff audit events"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Capture the identity snapshots once, at creation, and never overwrite
        # them afterwards (write-once immutability).
        if self._state.adding:
            from clients.services.activity import describe_actor

            if not self.actor_label:
                self.actor_label = describe_actor(self.actor)
            if not self.target_label:
                self.target_label = describe_actor(self.target)
        super().save(*args, **kwargs)

    @property
    def actor_display(self) -> str:
        return str(self.actor) if self.actor_id else (self.actor_label or "—")

    @property
    def target_display(self) -> str:
        return str(self.target) if self.target_id else (self.target_label or "—")

    def __str__(self) -> str:
        return f"{self.event_type} target={self.target_display}"
