from __future__ import annotations

from django.db import migrations
from django.utils import timezone


RU_LOG_PAGE_REPAIRS = [('Все статусы', ('Wszystkie statusy', 'All statuses'), 'Все статусы'),
 ('Статус', ('Status',), 'Статус'),
 ('С даты', ('Od daty', 'From date'), 'С даты'),
 ('По дату', ('Do daty', 'To date'), 'По дату'),
 ('Поиск', ('Szukaj', 'Search'), 'Поиск'),
 ('Тема или имя клиента...', ('Temat lub imię klienta...', 'Subject or client name...'), 'Тема или имя клиента...'),
 ('Все сотрудники', ('Wszyscy pracownicy', 'All staff'), 'Все сотрудники'),
 ('Сотрудник', ('Pracownik', 'Staff member'), 'Сотрудник'),
 ('Логи писем', ('Logi e-maili', 'Email Logs'), 'Логи писем'),
 ('Журнал отправленных писем клиентам.',
  ('Dziennik e-maili wyslanych do klientow.',
   'Dziennik wysłanych e-maili do klientów.',
   'Log of sent emails to clients.'),
  'Журнал отправленных писем клиентам.'),
 ('Дата отправки', ('Data wysłania', 'Sent date'), 'Дата отправки'),
 ('Клиент', ('Klient', 'Client'), 'Клиент'),
 ('Тема', ('Temat', 'Subject'), 'Тема'),
 ('Отправитель', ('Nadawca', 'Sender'), 'Отправитель'),
 ('Отправлено', ('Wysłano', 'Sent'), 'Отправлено'),
 ('В очереди', ('W kolejce', 'Queued'), 'В очереди'),
 ('Пропущено', ('Pominięto', 'Skipped'), 'Пропущено'),
 ('Ошибка', ('Błąd', 'Error'), 'Ошибка'),
 ('Система', ('System',), 'Система'),
 ('Логи писем не найдены.', ('Nie znaleziono logów e-maili.', 'No email logs found.'), 'Логи писем не найдены.'),
 ('Логи сотрудников', ('Logi pracowników', 'Staff logs', 'Staff Logs'), 'Логи сотрудников'),
 ('Просмотр всех значимых и незначимых действий, совершенных сотрудниками в системе.',
  ('Przeglad wszystkich istotnych i drobnych dzialan wykonanych przez pracownikow w systemie.',
   'Przegląd wszystkich istotnych i drobnych działań wykonanych przez pracowników w systemie.',
   'Przegląd wszystkich znaczących i nieznaczących działań wykonanych przez pracowników w systemie.',
   'View all significant and minor actions performed by staff in the system.'),
  'Просмотр всех значимых и незначимых действий, совершенных сотрудниками в системе.'),
 ('Клиент / Объект', ('Klient / obiekt', 'Klient / Obiekt', 'Client / Object'), 'Клиент / Объект'),
 ('Карточка клиента открыта', ('Karta klienta jest otwarta', 'Customer card is open'), 'Карточка клиента открыта'),
 ('Документ открыт', ('Dokument jest otwarty', 'The document is open'), 'Документ открыт'),
 ('Логи активности не найдены.',
  ('Nie znaleziono logów aktywności.', 'No activity logs found.'),
  'Логи активности не найдены.')]


def repair_ru_log_page_overrides(apps, schema_editor):
    TranslationOverride = apps.get_model("translations", "TranslationOverride")
    now = timezone.now()

    for msgid, wrong_texts, correct_text in RU_LOG_PAGE_REPAIRS:
        TranslationOverride.objects.filter(
            language="ru",
            msgid=msgid,
            is_active=True,
            text__in=wrong_texts,
        ).update(text=correct_text, source="import", updated_at=now)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("translations", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(repair_ru_log_page_overrides, noop_reverse),
    ]
