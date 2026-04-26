import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.translation import gettext as _

from clients.services.activity import log_client_activity
from .models import Client, Document, EmailLog, EmployeePermission, Payment, Reminder

logger = logging.getLogger(__name__)


@receiver(post_save, sender=get_user_model())
def ensure_employee_permissions_for_staff(sender, instance, created, **kwargs):
    if not getattr(instance, "is_staff", False):
        return
    if created:
        EmployeePermission.objects.get_or_create(user=instance)



@receiver(post_save, sender=Payment)
def sync_payment_reminder_on_save(sender, instance, **kwargs):
    if getattr(instance, "archived_at", None):
        Reminder.objects.filter(payment=instance).update(is_active=False)
        return

    if instance.status == "partial" and instance.due_date:
        Reminder.objects.update_or_create(
            payment=instance,
            defaults={
                "client": instance.client,
                "reminder_type": "payment",
                "title": _("Второй платёж: %(service)s") % {
                    "service": instance.get_service_description_display(),
                },
                "notes": _("Остаток: %(amount)s zł. Счёт №%(number)s") % {
                    "amount": instance.amount_due,
                    "number": instance.id,
                },
                "due_date": instance.due_date,
                "is_active": True,
            },
        )
    else:
        Reminder.objects.filter(payment=instance).delete()


@receiver(pre_save, sender=Payment)
def deactivate_payment_reminders_on_archive(sender, instance, **kwargs):
    if not instance.pk or not getattr(instance, "archived_at", None):
        return
    try:
        previous = Payment.all_objects.get(pk=instance.pk)
    except Payment.DoesNotExist:
        return
    if previous.archived_at is None and instance.archived_at is not None:
        Reminder.objects.filter(payment=instance, is_active=True).update(is_active=False)


@receiver(pre_save, sender=Client)
def deactivate_user_account_when_client_archived(sender, instance, **kwargs):
    if not instance.pk or not instance.user_id or not getattr(instance, "archived_at", None):
        return

    try:
        previous = Client.all_objects.get(pk=instance.pk)
    except Client.DoesNotExist:
        return

    if previous.archived_at is not None or instance.archived_at is None:
        return

    UserModel = get_user_model()
    try:
        user = UserModel.objects.get(pk=instance.user_id)
    except UserModel.DoesNotExist:
        return

    if user.is_staff or not user.is_active:
        return

    user.is_active = False
    user.save(update_fields=["is_active"])


@receiver(pre_save, sender=Client)
def sync_payment_service_check(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        old_instance = Client.all_objects.get(pk=instance.pk)
    except Client.DoesNotExist:
        return

    if old_instance.application_purpose != instance.application_purpose:
        purpose_map = {
            "work": "work_service",
            "study": "study_service",
            "family": "consultation",
        }

        new_service = purpose_map.get(instance.application_purpose)
        if new_service:
            Payment.objects.filter(client=instance, status="pending").update(service_description=new_service)


@receiver(pre_save, sender=Document)
def compress_document_image_on_upload(sender, instance, **kwargs):
    from clients.services.image_compression import compress_uploaded_file, should_compress

    if not instance.file:
        return

    is_new_upload = not instance.pk
    file_changed = False

    if not is_new_upload:
        try:
            old_instance = Document.all_objects.get(pk=instance.pk)
            file_changed = old_instance.file != instance.file
        except Document.DoesNotExist:
            is_new_upload = True

    if not (is_new_upload or file_changed):
        return

    if not should_compress(instance.file.name):
        return

    try:
        compressed_file = compress_uploaded_file(instance.file)
        if compressed_file:
            instance.file = compressed_file
    except Exception:
        logger.warning("Failed to compress document %s, keeping original", instance.file.name)


@receiver(post_save, sender=EmailLog)
def create_activity_for_email_log(sender, instance, created, **kwargs):
    if not created or not instance.client_id:
        return

    log_client_activity(
        client=instance.client,
        actor=instance.sent_by,
        event_type="email_sent",
        summary=f"Отправлено письмо: {instance.subject}",
        metadata={
            "email_log_id": instance.pk,
            "template_type": instance.template_type,
            "recipients_count": len([item for item in (instance.recipients or "").split(",") if item.strip()]),
        },
    )
