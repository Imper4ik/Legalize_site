import os
import django
import sys

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legalize_site.settings.development")
django.setup()

from datetime import timedelta
from django.utils import timezone
from clients.models import Client, Reminder, EmailLog
from django.core.management import call_command

# Удаляем старого тестового клиента, если есть
Client.all_objects.filter(email="zus-test@example.com").delete()

today = timezone.localdate()
# Клиент сдал отпечатки 90 дней назад (3 месяца)
fingerprints_date = today - timedelta(days=90)

client = Client.objects.create(
    email="zus-test@example.com",
    first_name="Zus",
    last_name="Test",
    citizenship="Test",
    phone="+48000111222",
    workflow_stage="waiting_decision",
    fingerprints_date=fingerprints_date,
    application_purpose="work"
)

print(f"--- Создан тестовый клиент ---")
print(f"Имя: {client.get_full_name()}")
print(f"Дата отпечатков: {client.fingerprints_date}")
print(f"Текущая дата: {today}")
print("------------------------------\n")

print("Запуск команды update_reminders (проверка ZUS RCA)...")
call_command("update_reminders", "--only", "zus")
print("------------------------------\n")

reminders = Reminder.objects.filter(client=client)
emails = EmailLog.objects.filter(client=client)

print(f"=== Результат ===")
print(f"Сгенерировано напоминаний в CRM: {reminders.count()}")
for r in reminders:
    print(f" - [{r.due_date}] {r.title}: {r.notes}")

print(f"\nСгенерировано писем (Email): {emails.count()}")
for e in emails:
    print(f" - [{e.template_type}] {e.subject} (Статус: {e.delivery_status})")

# Очистка
Client.all_objects.filter(email="zus-test@example.com").delete()
