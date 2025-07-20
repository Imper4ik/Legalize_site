# clients/management/commands/update_reminders.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction  # Импортируем для атомарных операций
from clients.models import Document, Payment, Reminder


class Command(BaseCommand):
    help = 'Создает напоминания по документам и предстоящим оплатам, обеспечивая целостность данных.'

    def handle(self, *args, **options):
        """
        Главный метод команды. Последовательно запускает создание напоминаний.
        """
        self.stdout.write(self.style.SUCCESS("--- Начинаю проверку напоминаний ---"))

        # Используем transaction.atomic, чтобы гарантировать, что либо все напоминания
        # в рамках одной функции будут созданы, либо ни одного, если произойдет ошибка.
        try:
            with transaction.atomic():
                self.stdout.write(self.style.HTTP_INFO("-> Запускаю проверку документов..."))
                self.create_document_reminders()

            with transaction.atomic():
                self.stdout.write(self.style.HTTP_INFO("-> Запускаю проверку оплат..."))
                self.create_payment_reminders()

            self.stdout.write(self.style.SUCCESS("--- Проверка успешно завершена ---"))

        except Exception as e:
            # Если что-то пойдет не так, мы увидим ошибку в консоли
            self.stdout.write(self.style.ERROR(f"Произошла ошибка во время создания напоминаний: {e}"))
            self.stdout.write(self.style.ERROR("--- Проверка прервана ---"))


    def create_document_reminders(self):
        """
        Создает напоминания для документов, у которых скоро истекает срок.
        Проверка `reminder__isnull=True` гарантирует, что мы не создадим дубликат
        благодаря связи OneToOneField в модели Reminder.
        """
        today = timezone.now().date()
        reminder_period_end = today + timedelta(days=30) # Период напоминания - 30 дней

        # Ищем документы, которые истекают в ближайшие 30 дней и для которых еще нет напоминания
        expiring_docs = Document.objects.filter(
            expiry_date__isnull=False, # Убедимся, что дата окончания срока вообще установлена
            expiry_date__range=(today, reminder_period_end),
            reminder__isnull=True  # Ключевая проверка: напоминание еще не создано
        )

        if not expiring_docs.exists():
            self.stdout.write('Документов с истекающим сроком для создания напоминаний не найдено.')
            return

        count = 0
        for doc in expiring_docs:
            # Создаем новое напоминание
            Reminder.objects.create(
                client=doc.client,
                document=doc,  # Связываем с конкретным документом
                title=f"Истекает срок документа: {doc.get_document_type_display()}",
                notes=f"Документ для клиента {doc.client} действителен до {doc.expiry_date.strftime('%d.%m.%Y')}.",
                due_date=doc.expiry_date,
                reminder_type='document'
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Создано {count} новых напоминаний по документам.'))


    def create_payment_reminders(self):
        """
        Создает напоминания для счетов, которые нужно оплатить сегодня.
        Проверка `reminder__isnull=True` также предотвращает дублирование.
        """
        today = timezone.now().date()

        # Ищем неоплаченные или частично оплаченные счета с датой оплаты сегодня,
        # для которых еще нет напоминания.
        due_payments = Payment.objects.filter(
            due_date=today,
            status__in=['pending', 'partial'], # Только для неоплаченных счетов
            reminder__isnull=True  # Ключевая проверка: напоминание еще не создано
        )

        if not due_payments.exists():
            self.stdout.write('Счетов для создания напоминаний об оплате на сегодня не найдено.')
            return

        count = 0
        for payment in due_payments:
            # Создаем новое напоминание
            Reminder.objects.create(
                client=payment.client,
                payment=payment, # Связываем с конкретным счетом
                title=f"Сегодня срок оплаты: {payment.get_service_description_display()}",
                notes=f"Счет на сумму {payment.total_amount} для клиента {payment.client}. Осталось оплатить: {payment.amount_due}.",
                due_date=payment.due_date,
                reminder_type='payment'
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f'Создано {count} новых напоминаний по оплатам.'))