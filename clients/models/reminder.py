from django.db import models
from django.utils.translation import gettext_lazy as _

class Reminder(models.Model):
    REMINDER_TYPE_CHOICES = [
        ('payment', _('Оплата')),
        ('document', _('Документ')),
        ('other', _('Другое')),
    ]

    client = models.ForeignKey('clients.Client', on_delete=models.CASCADE, related_name='reminders', verbose_name=_("Клиент"))
    payment = models.OneToOneField('clients.Payment', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    document = models.OneToOneField('clients.Document', on_delete=models.CASCADE, null=True, blank=True, related_name="reminder")
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPE_CHOICES, default='document',
                                     verbose_name=_("Тип напоминания"))
    title = models.CharField(max_length=255, verbose_name=_("Заголовок напоминания"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Детали"))
    due_date = models.DateField(verbose_name=_("Ключевая дата"))
    is_active = models.BooleanField(default=True, verbose_name=_("Активно"))
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Напоминание для {self.client}: {self.title}"

    class Meta:
        ordering = ['due_date']
