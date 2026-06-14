from __future__ import annotations

from django.db import models
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _


class Reminder(models.Model):
    REMINDER_TYPE_CHOICES = [
        ('payment', _('Оплата')),
        ('document', _('Документ')),
        ('legal_stay', _('Легальное пребывание')),
        ('other', _('Другое')),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='reminders', verbose_name=_("Клиент"))
    payment = models.OneToOneField('clients.Payment', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    document = models.OneToOneField('clients.Document', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    custom_document_requirement = models.ForeignKey(
        "clients.ClientDocumentRequirement",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="reminders",
    )
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES, default='document',
                                     verbose_name=_("Тип напоминания"))
    title = models.CharField(max_length=255, verbose_name=_("Заголовок напоминания"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Детали"))
    due_date = models.DateField(verbose_name=_("Ключевая дата"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_title(self) -> str:
        if self.custom_document_requirement:
            return gettext("Нужно предоставить документ: %(name)s") % {
                "name": self.custom_document_requirement.name
            }
        if self.reminder_type == 'document' and self.document:
            return gettext("Истекает срок действия документа: %(name)s") % {
                "name": self.document.display_name
            }
        if self.reminder_type == 'payment' and self.payment:
            return gettext("Просрочен платеж: %(service)s") % {
                "service": self.payment.get_service_description_display()
            }
        if self.reminder_type == 'legal_stay':
            due_str = self.due_date.strftime('%d.%m.%Y') if self.due_date else ""
            return gettext("Истекает легальное пребывание: %(date)s") % {
                "date": due_str
            }
        return self.title

    @property
    def display_notes(self) -> str:
        if self.custom_document_requirement:
            return self.custom_document_requirement.description or self.notes or ""
        if self.reminder_type == 'document' and self.document:
            expiry_str = self.document.expiry_date.strftime('%d.%m.%Y') if self.document.expiry_date else ""
            return gettext("Документ для клиента %(client)s истекает %(date)s.") % {
                "client": str(self.client),
                "date": expiry_str
            }
        if self.reminder_type == 'payment' and self.payment:
            total_str = f"{self.payment.total_amount:.2f}"
            due_str = f"{self.payment.amount_due:.2f}"
            return gettext("Сумма к оплате: %(total)s; долг: %(due)s; клиент: %(client)s.") % {
                "total": total_str,
                "due": due_str,
                "client": str(self.client),
            }
        if self.reminder_type == 'legal_stay' and self.client:
            try:
                mos = self.client.mos_application_data
                if mos and mos.legal_stay_until:
                    stay_str = mos.legal_stay_until.strftime('%d.%m.%Y')
                    due_str = self.due_date.strftime('%d.%m.%Y') if self.due_date else ""
                    return gettext("По срокам: %(stay_until)s. Сдвиг дедлайна с учетом выходных: %(due_date)s.") % {
                        "stay_until": stay_str,
                        "due_date": due_str
                    }
            except Exception:
                pass
        return self.notes or ""

    def __str__(self) -> str:
        return f"Напоминание для {self.client}: {self.title}"

    class Meta:
        ordering = ['due_date']
        indexes = [
            models.Index(fields=["is_active", "due_date"], name="reminder_active_due_idx"),
            models.Index(fields=["client", "is_active"], name="reminder_client_active_idx"),
        ]
