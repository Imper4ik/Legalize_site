from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ClientActivity(models.Model):
    EVENT_TYPE_CHOICES = [
        ("client_viewed", _("Карточка клиента открыта")),
        ("client_created", _("Клиент создан")),
        ("client_updated", _("Данные клиента изменены")),
        ("workflow_changed", _("Этап workflow изменён")),
        ("document_uploaded", _("Документ загружен")),
        ("document_downloaded", _("Документ открыт")),
        ("document_deleted", _("Документ удалён")),
        ("document_verified", _("Статус документа изменён")),
        ("document_version_restored", _("Версия документа восстановлена")),
        ("email_sent", _("Письмо отправлено")),
        ("client_exported", _("Данные клиента экспортированы")),
        ("wniosek_attachment_deleted", _("Отметка wniosek удалена")),
        ("reminder_deactivated", _("Напоминание отмечено выполненным")),
        ("reminder_deleted", _("Напоминание удалено")),
        ("payment_created", _("Платёж создан")),
        ("payment_updated", _("Платёж обновлён")),
        ("payment_deleted", _("Платёж удалён")),
        ("task_created", _("Задача создана")),
        ("task_completed", _("Задача завершена")),
        ("note_updated", _("Заметка обновлена")),
    ]

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name=_("Клиент"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="client_activities",
        verbose_name=_("Сотрудник"),
    )
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE_CHOICES, verbose_name=_("Тип события"))
    summary = models.CharField(max_length=255, verbose_name=_("Краткое описание"))
    details = models.TextField(blank=True, verbose_name=_("Детали"))
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Метаданные"))
    document = models.ForeignKey(
        "clients.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name=_("Документ"),
    )
    payment = models.ForeignKey(
        "clients.Payment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name=_("Платёж"),
    )
    task = models.ForeignKey(
        "clients.StaffTask",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activities",
        verbose_name=_("Задача"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Событие клиента")
        verbose_name_plural = _("События клиентов")

    def __str__(self):
        return f"[{self.created_at:%d.%m.%Y %H:%M}] {self.summary}"

    @property
    def actor_display(self) -> str:
        if not self.actor:
            return str(_("Система"))
        full_name = self.actor.get_full_name().strip()
        return full_name or getattr(self.actor, "email", str(self.actor))

    @property
    def badge_class(self) -> str:
        badge_map = {
            "client_viewed": "bg-light text-dark",
            "client_created": "bg-primary",
            "client_updated": "bg-primary",
            "workflow_changed": "bg-info text-dark",
            "document_uploaded": "bg-success",
            "document_downloaded": "bg-secondary",
            "document_deleted": "bg-danger",
            "document_verified": "bg-success",
            "document_version_restored": "bg-info text-dark",
            "email_sent": "bg-warning text-dark",
            "client_exported": "bg-dark",
            "wniosek_attachment_deleted": "bg-secondary",
            "reminder_deactivated": "bg-secondary",
            "reminder_deleted": "bg-danger",
            "payment_created": "bg-primary",
            "payment_updated": "bg-info text-dark",
            "payment_deleted": "bg-danger",
            "task_created": "bg-primary",
            "task_completed": "bg-success",
            "note_updated": "bg-secondary",
        }
        return badge_map.get(self.event_type, "bg-secondary")
