# clients/management/commands/create_document_reminders.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from clients.models import Document, Reminder


class Command(BaseCommand):
    help = 'Создает напоминания для документов, срок действия которых скоро истекает'

    def handle(self, *args, **options):
        today = timezone.now().date()
        # Искать документы, которые истекают в ближайшие 30 дней
        reminder_period_end = today + timedelta(days=30)

        # Находим документы, которые скоро истекают и для которых еще НЕТ напоминания
        expiring_docs = Document.objects.filter(
            expiry_date__range=(today, reminder_period_end),
            reminder__isnull=True  # Проверяем, что напоминание не создано
        )

        count = 0
        for doc in expiring_docs:
            Reminder.objects.create(
                client=doc.client,
                document=doc, # Связываем напоминание с документом
                title=f"Истекает срок документа: {doc.get_document_type_display()}",
                due_date=doc.expiry_date,
                reminder_type='document'
            )
            count += 1

        self.stdout.write(self.style.SUCCESS(f'Успешно создано {count} новых напоминаний по документам.'))