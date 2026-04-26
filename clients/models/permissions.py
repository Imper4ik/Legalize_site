from __future__ import annotations

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
