# clients/management/commands/create_reminders.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from clients.models import Client, Reminder


class Command(BaseCommand):
    help = 'Создает напоминания для предстоящих окончания документов'

    def handle(self, *args, **options):
        today = timezone.now().date()
        reminder_period = today + timedelta(days=30)

        self.stdout.write("Начинаю проверку и создание напоминаний по документам...")

        clients_with_ending_basis = Client.objects.filter(legal_basis_end_date__isnull=False, legal_basis_end_date__lte=reminder_period)

        for client in clients_with_ending_basis:
            reminder_exists = Reminder.objects.filter(
                client=client,
                reminder_type='document',
                due_date=client.legal_basis_end_date
            ).exists()

            if not reminder_exists:
                Reminder.objects.create(
                    client=client,
                    reminder_type='document',
                    title=f"Окончание основания: {client.basis_of_stay}",
                    due_date=client.legal_basis_end_date
                )
                self.stdout.write(self.style.SUCCESS(f"Создано напоминание об окончании документа для {client}"))

        self.stdout.write("Проверка по документам завершена.")