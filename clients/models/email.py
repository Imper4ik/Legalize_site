from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

class EmailLog(models.Model):
    """Журнал отправленных писем клиентам."""
    client = models.ForeignKey(
        'clients.Client', on_delete=models.CASCADE, related_name='email_logs',
        verbose_name=_("Клиент"), null=True, blank=True,
    )
    subject = models.CharField(max_length=500, verbose_name=_("Тема"))
    body = models.TextField(verbose_name=_("Текст письма"))
    recipients = models.CharField(max_length=500, verbose_name=_("Получатели"))
    template_type = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name=_("Тип шаблона"),
    )
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Дата отправки"))
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name=_("Отправитель"),
    )

    class Meta:
        ordering = ['-sent_at']
        verbose_name = _("Журнал email")
        verbose_name_plural = _("Журнал email")

    def __str__(self):
        return f"[{self.sent_at:%d.%m.%Y %H:%M}] {self.subject} → {self.recipients}"
