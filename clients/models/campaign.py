"""Email campaign tracking model for asynchronous mass email delivery."""

import json

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedTextField


class EmailCampaign(models.Model):
    """Tracks the progress and outcome of a mass email sending job."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, _("В очереди")),
        (STATUS_RUNNING, _("Отправка")),
        (STATUS_COMPLETED, _("Завершено")),
        (STATUS_FAILED, _("Ошибка")),
    ]

    subject = models.CharField(max_length=500, verbose_name=_("Тема"))
    message = EncryptedTextField(verbose_name=_("Текст письма"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name=_("Статус"),
    )
    total_recipients = models.PositiveIntegerField(default=0, verbose_name=_("Всего получателей"))
    sent_count = models.PositiveIntegerField(default=0, verbose_name=_("Отправлено"))
    failed_count = models.PositiveIntegerField(default=0, verbose_name=_("Ошибок"))
    recipient_emails = EncryptedTextField(default="[]", blank=True, verbose_name=_("Получатели"))
    filters_snapshot = models.JSONField(default=dict, blank=True, verbose_name=_("Фильтры"))
    error_details = EncryptedTextField(blank=True, default="", verbose_name=_("Детали ошибок"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Запущено"))
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Завершено"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Инициатор"),
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Email-кампания")
        verbose_name_plural = _("Email-кампании")

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} ({self.sent_count}/{self.total_recipients})"

    @property
    def recipient_emails_list(self) -> list[str]:
        raw_value = self.recipient_emails
        if isinstance(raw_value, list):
            return [str(item) for item in raw_value]
        if not raw_value:
            return []
        if isinstance(raw_value, str):
            try:
                decoded = json.loads(raw_value)
                if isinstance(decoded, list):
                    return [str(item) for item in decoded]
            except json.JSONDecodeError:
                legacy_items = [part.strip() for part in raw_value.split(",") if part.strip()]
                return legacy_items
        return []

    def set_recipient_emails(self, recipients: list[str]) -> None:
        self.recipient_emails = json.dumps([str(item) for item in recipients])

    def save(self, *args, **kwargs):
        if isinstance(self.recipient_emails, list):
            self.set_recipient_emails([str(item) for item in self.recipient_emails])
        super().save(*args, **kwargs)
