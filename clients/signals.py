# clients/signals.py
from django.conf import settings
from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from .models import Payment, Reminder, Client, Document


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
                'title': _("Второй платёж: %(service)s") % {
                    "service": instance.get_service_description_display(),
                },
                'notes': _("Остаток: %(amount)s zł. Счёт №%(number)s") % {
                    "amount": instance.amount_due,
                    "number": instance.id,
                },
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


# --- Очистка учётной записи при удалении клиента ---
@receiver(post_delete, sender=Client)
def delete_user_account_when_client_removed(sender, instance, **kwargs):
    """Удаляет привязанного пользователя, чтобы освободить email для новой регистрации."""

    if not instance.user_id:
        return

    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=instance.user_id)
    except UserModel.DoesNotExist:
        return

    if user.is_staff:
        return

    user.delete()


# --- НОВЫЙ СИГНАЛ: Автоматически создаёт профиль клиента ---
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_client_profile_for_new_user(sender, instance, created, **kwargs):
    """
    Создает профиль клиента для каждого нового зарегистрированного пользователя.
    """
    if not created or instance.is_staff:
        return

    # Для корректного создания требуются обязательные поля модели Client.
    required_fields = ('first_name', 'last_name', 'email', 'phone', 'citizenship')
    defaults = {field: getattr(instance, field, '') for field in required_fields}

    if not defaults['email']:
        return

    # Если какие-то обязательные поля отсутствуют, не создаём пустой профиль,
    # чтобы избежать IntegrityError. Профиль будет создан через форму.
    if any(not defaults[field] for field in ('first_name', 'last_name', 'phone', 'citizenship')):
        return

    Client.objects.get_or_create(user=instance, defaults=defaults)


@receiver(post_delete, sender=Document)
def delete_document_file_on_delete(sender, instance, **kwargs):
    """
    Автоматически удаляет связанный файл при УДАЛЕНИИ объекта Document.
    """
    if instance.file:
        instance.file.delete(save=False)



@receiver(pre_save, sender=Client)
def sync_payment_service_check(sender, instance, **kwargs):
    """
    Отслеживает изменение цели подачи (application_purpose).
    Если цель изменилась, обновляем service_description для всех PENDING платежей.
    """
    if not instance.pk:
        return

    try:
        # Fetch the object directly from the database to compare
        old_instance = Client.objects.get(pk=instance.pk)
    except Client.DoesNotExist:
        return

    # Check if application_purpose has changed
    if old_instance.application_purpose != instance.application_purpose:
        # Карта соответствия целей и услуг
        purpose_map = {
            'work': 'work_service',
            'study': 'study_service',
            'family': 'consultation',
        }
        
        new_service = purpose_map.get(instance.application_purpose)
        if new_service:
            # Update pending payments safely
            Payment.objects.filter(client=instance, status='pending').update(service_description=new_service)

