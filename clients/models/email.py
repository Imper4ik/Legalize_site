from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedTextField


class EmailLog(models.Model):
    """Журнал отправленных писем клиентам."""

    DELIVERY_STATUS_QUEUED = "queued"
    DELIVERY_STATUS_SENT = "sent"
    DELIVERY_STATUS_SKIPPED = "skipped"
    DELIVERY_STATUS_FAILED = "failed"
    DELIVERY_STATUS_CHOICES = [
        (DELIVERY_STATUS_QUEUED, _("В очереди")),
        (DELIVERY_STATUS_SENT, _("Отправлено")),
        (DELIVERY_STATUS_SKIPPED, _("Пропущено")),
        (DELIVERY_STATUS_FAILED, _("Ошибка")),
    ]

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="email_logs",
        verbose_name=_("Клиент"),
        null=True,
        blank=True,
    )
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.SET_NULL,
        related_name="email_logs",
        verbose_name=_("Дело"),
        null=True,
        blank=True,
    )
    subject = models.CharField(max_length=500, verbose_name=_("Тема"))
    body = EncryptedTextField(verbose_name=_("Текст письма"))
    recipients = EncryptedTextField(verbose_name=_("Получатели"))
    template_type = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("Тип шаблона"),
    )
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата отправки"))
    delivery_status = models.CharField(
        max_length=20,
        choices=DELIVERY_STATUS_CHOICES,
        default=DELIVERY_STATUS_SENT,
        verbose_name=_("Статус доставки"),
    )
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("Ключ идемпотентности"),
    )
    error_message = EncryptedTextField(blank=True, default="", verbose_name=_("Ошибка доставки"))
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Отправитель"),
    )

    is_test_data = models.BooleanField(default=False, db_index=True)
    is_demo_data = models.BooleanField(default=False, db_index=True)

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
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
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_legacy_compatibility_case
            self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = _("Журнал email")
        verbose_name_plural = _("Журнал email")
        indexes = [
            models.Index(fields=["client", "-sent_at"], name="emaillog_client_sent_idx"),
            models.Index(fields=["case", "-sent_at"], name="emaillog_case_sent_idx"),
            models.Index(fields=["client", "template_type"], name="emaillog_client_tmpl_idx"),
            models.Index(fields=["delivery_status", "-sent_at"], name="emaillog_status_sent_idx"),
            models.Index(fields=["-sent_at"], name="emaillog_sent_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="clients_emaillog_unique_idempotency_key",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.sent_at:%d.%m.%Y %H:%M}] {self.subject} -> {self.recipients}"
