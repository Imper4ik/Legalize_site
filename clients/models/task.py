from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class StaffTask(models.Model):
    STATUS_CHOICES = [
        ("open", _("Открыта")),
        ("in_progress", _("В работе")),
        ("done", _("Завершена")),
        ("cancelled", _("Отменена")),
    ]
    PRIORITY_CHOICES = [
        ("low", _("Низкий")),
        ("medium", _("Средний")),
        ("high", _("Высокий")),
        ("urgent", _("Срочный")),
    ]

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="staff_tasks",
        verbose_name=_("Клиент"),
    )
    title = models.CharField(max_length=255, verbose_name=_("Задача"))
    description = models.TextField(blank=True, verbose_name=_("Описание"))
    due_date = models.DateField(null=True, blank=True, verbose_name=_("Срок"))
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default="medium",
        verbose_name=_("Приоритет"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="open",
        verbose_name=_("Статус"),
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_client_tasks",
        verbose_name=_("Ответственный"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_client_tasks",
        verbose_name=_("Создал"),
    )
    document = models.ForeignKey(
        "clients.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_tasks",
        verbose_name=_("Документ"),
    )
    payment = models.ForeignKey(
        "clients.Payment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_tasks",
        verbose_name=_("Платёж"),
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Завершена"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создана"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлена"))

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        verbose_name = _("Задача сотрудника")
        verbose_name_plural = _("Задачи сотрудников")

    def __str__(self):
        return self.title

    @property
    def is_open(self) -> bool:
        return self.status in {"open", "in_progress"}

    @property
    def assignee_display(self) -> str:
        if not self.assignee:
            return str(_("Не назначен"))
        full_name = self.assignee.get_full_name().strip()
        return full_name or getattr(self.assignee, "email", str(self.assignee))

    @property
    def priority_badge_class(self) -> str:
        badge_map = {
            "low": "bg-secondary",
            "medium": "bg-info text-dark",
            "high": "bg-warning text-dark",
            "urgent": "bg-danger",
        }
        return badge_map.get(self.priority, "bg-secondary")

    @property
    def status_badge_class(self) -> str:
        badge_map = {
            "open": "bg-primary",
            "in_progress": "bg-warning text-dark",
            "done": "bg-success",
            "cancelled": "bg-secondary",
        }
        return badge_map.get(self.status, "bg-secondary")

    def mark_done(self, *, save: bool = True) -> None:
        self.status = "done"
        self.completed_at = timezone.now()
        if save:
            self.save(update_fields=["status", "completed_at", "updated_at"])
