# clients/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Payment, Reminder

@receiver(post_save, sender=Payment)
def sync_payment_reminder_on_save(sender, instance, **kwargs):
    """
    Автоматически создает или обновляет напоминание при ИЗМЕНЕНИИ платежа.
    """
    if instance.status == 'partial' and instance.due_date:
        Reminder.objects.update_or_create(
            payment=instance,
            defaults={
                'client': instance.client,
                'reminder_type': 'payment',
                'title': f"Второй платёж: {instance.get_service_description_display()}",
                'notes': f"Остаток: {instance.amount_due} zł. Счёт №{instance.id}",
                'due_date': instance.due_date,
                'is_active': True
            }
        )
    else:
        Reminder.objects.filter(payment=instance).delete()

# --- НОВЫЙ СИГНАЛ: Реагирует на УДАЛЕНИЕ платежа ---
@receiver(post_delete, sender=Payment)
def sync_payment_reminder_on_delete(sender, instance, **kwargs):
    """
    Автоматически удаляет связанное напоминание при УДАЛЕНИИ платежа.
    """
    Reminder.objects.filter(payment=instance).delete()