from __future__ import annotations

from typing import Any, Self

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from clients.models.consistency import assert_case_client_consistent


class StaffTaskQuerySet(models.QuerySet):
    def for_active_cases(self) -> Self:
        return self.filter(case__isnull=False, case__archived_at__isnull=True)


class StaffTask(models.Model):
    objects = models.Manager.from_queryset(StaffTaskQuerySet)()

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

    TASK_TYPE_CHOICES = [
        ("document_review", _("Проверка документов")),
        ("missing_document", _("Недостающий документ")),
        ("zus_update", _("Обновление ZUS")),
        ("case_number_missing", _("Отсутствует номер дела")),
        ("fingerprints_followup", _("Контроль после отпечатков")),
        ("payment_followup", _("Контроль оплаты")),
        ("client_question", _("Вопрос клиента")),
        ("internal_note", _("Внутренняя заметка")),
        ("deadline_check", _("Контроль дедлайна")),
    ]

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="staff_tasks",
        verbose_name=_("Клиент"),
    )
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_tasks",
        verbose_name=_("Дело"),
    )
    task_type = models.CharField(
        max_length=50,
        choices=TASK_TYPE_CHOICES,
        default="internal_note",
        verbose_name=_("Тип задачи"),
    )
    is_auto_created = models.BooleanField(
        default=False,
        verbose_name=_("Создана автоматически"),
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
    suspended_by_case_archive = models.BooleanField(default=False, verbose_name=_("Приостановлена архивацией дела"))
    suspended_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Дата приостановки"))
    suspended_by_archive_batch = models.ForeignKey(
        "clients.CaseArchiveBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="suspended_tasks",
        verbose_name=_("Батч архивации"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создана"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлена"))
    version = models.PositiveIntegerField(default=1, verbose_name=_("Версия"))

    class Meta:
        ordering = ["status", "due_date", "-created_at"]
        verbose_name = _("Задача сотрудника")
        verbose_name_plural = _("Задачи сотрудников")
        indexes = [
            models.Index(fields=["status", "due_date"], name="task_status_due_idx"),
            models.Index(fields=["client", "status", "due_date"], name="task_client_status_due_idx"),
            models.Index(fields=["case", "status", "due_date"], name="task_case_status_due_idx"),
            models.Index(fields=["assignee", "status", "due_date"], name="task_assignee_status_due_idx"),
        ]

    def _resolve_source_case_id(self) -> int | None:
        """Case id implied by the task's source object, if any (document first)."""
        for source in (self.document, self.payment):
            if source is not None and source.case_id:
                return source.case_id
        return None

    def clean(self) -> None:
        super().clean()
        source_case_id = self._resolve_source_case_id()

        if self.case_id is None:
            if source_case_id is not None:
                self.case_id = source_case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                try:
                    self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")

        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        source_case_id = self._resolve_source_case_id()
        if self.case_id is None:
            if source_case_id is not None:
                self.case_id = source_case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if self.case_id is not None and update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.title)

    @property
    def is_client_question(self) -> bool:
        return self.description.startswith("Клиент задал вопрос через приложение:")

    @property
    def communication_url(self) -> str:
        from django.urls import reverse

        return f"{reverse('clients:client_detail', kwargs={'pk': self.client_id})}?tab=history#communication-history"

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
