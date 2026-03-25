from django.db import models
from django.utils.translation import gettext_lazy as _

class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('pending', _('Ожидает оплаты')),
        ('partial', _('Частично оплачен')),
        ('paid', _('Оплачен полностью')),
        ('refunded', _('Возврат')),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('card', _('Карта')),
        ('cash', _('Наличные')),
        ('transfer', _('Перевод')),
        ('blik', _('BLIK')),
    ]
    SERVICE_CHOICES = [
        ('work_service', _('Работа')),
        ('study_service', _('Учёба')),
        ('consultation', _('Консультация')),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='payments', verbose_name=_("Клиент"))
    service_description = models.CharField(max_length=100, choices=SERVICE_CHOICES, verbose_name=_("Описание услуги"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_("Общая сумма"))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name=_("Оплаченная сумма"))
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending',
                              verbose_name=_("Статус оплаты"))
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True,
                                      verbose_name=_("Способ оплаты"))
    payment_date = models.DateField(blank=True, null=True, verbose_name=_("Дата оплаты"))
    due_date = models.DateField(blank=True, null=True, verbose_name=_("Срок оплаты"))
    transaction_id = models.CharField(max_length=100, blank=True, null=True, verbose_name=_("ID транзакции"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Создано"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Обновлено"))

    def __str__(self):
        return f"Счёт {self.pk} - {self.client} ({self.total_amount} PLN)"

    class Meta:
        ordering = ['-created_at']
        verbose_name = _("Платёж")
        verbose_name_plural = _("Платежи")
