from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedTextField


class EmailLog(models.Model):
    """Журнал отправленных писем клиентам."""

    DELIVERY_STATUS_SENT = "sent"
    DELIVERY_STATUS_SKIPPED = "skipped"
    DELIVERY_STATUS_FAILED = "failed"
    DELIVERY_STATUS_CHOICES = [
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

    class Meta:
        ordering = ["-sent_at"]
        verbose_name = _("Журнал email")
        verbose_name_plural = _("Журнал email")
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="clients_emaillog_unique_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"[{self.sent_at:%d.%m.%Y %H:%M}] {self.subject} -> {self.recipients}"
