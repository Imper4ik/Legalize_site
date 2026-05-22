import polib

en_dict = {
    "Управление рабочими настройками базы без Django admin.": "Manage database settings without Django admin.",
    "Ожидают оплаты": "Awaiting payment",
    "Шаблоны": "Templates",
    "Глобальные значения для печатных документов текущей базы.": "Global values for printable documents of the current database.",
    "Чеклисты": "Checklists",
    "Обязательные документы и структура checklist по типу подачи.": "Mandatory documents and checklist structure by submission type.",
    "Основания подачи": "Submission types",
    "Список submission types, статусы и локализованные названия в рабочем интерфейсе.": "List of submission types, statuses and localized names in the working interface.",
    "Цены и услуги": "Prices and services",
    "Рабочий прайс без Django admin.": "Working price list without Django admin.",
    "Записей:": "Records:",
    "Сумма прайса:": "Total price:",
    "Сотрудники": "Staff",
    "Управление staff-аккаунтами, доступом и рабочими ролями.": "Management of staff accounts, access and working roles.",
    "Роли": "Roles",
    "Система": "System",
    "Техническое состояние, runtime checks и health dashboard.": "Technical state, runtime checks and health dashboard.",
    "Метрики": "Metrics",
    "Быстрый переход к аналитике и воронке.": "Quick navigation to analytics and funnel.",
    "Журналы системы": "System logs",
    "Просмотр отправленных писем и действий сотрудников (логи аудита).": "View sent emails and staff actions (audit logs).",
    "Создать новое основание": "Create new submission type",
    "Название (внутреннее)": "Name (internal)",
    "Статус": "Status",
    "Создать": "Create",
    "Существующие основания": "Existing submission types",
    "Слаг": "Slug",
    "Действия": "Actions",
    "Сохранить": "Save",
    "Удалить это основание?": "Delete this submission type?",
    "Удалить": "Delete",
    "Нет добавленных оснований.": "No submission types added.",
    "Управление ценами на услуги.": "Service price management.",
    "Описание": "Description",
    "Цена PLN": "Price PLN",
    "Сохранить изменения": "Save changes",
    "Active cases": "Active cases",
    "OCR awaiting review": "OCR awaiting review",
    "No documents awaiting OCR": "No documents awaiting OCR",
    "Documents awaiting verification": "Documents awaiting verification",
    "Missing documents": "Missing documents",
    "Expired documents": "Expired documents",
    "No expired documents": "No expired documents",
    "Upcoming fingerprints": "Upcoming fingerprints",
    "Waiting after fingerprints": "Waiting after fingerprints",
    "Decisions": "Decisions",
    "Active reminders": "Active reminders",
    "No active reminders": "No active reminders",
}

pl_dict = {
    "Управление рабочими настройками базы без Django admin.": "Zarządzanie ustawieniami bazy bez Django admin.",
    "Ожидают оплаты": "Oczekują na płatność",
    "Шаблоны": "Szablony",
    "Глобальные значения для печатных документов текущей базы.": "Globalne wartości dla dokumentów do druku obecnej bazy.",
    "Чеклисты": "Listy kontrolne",
    "Обязательные документы и структура checklist по типу подачи.": "Obowiązkowe dokumenty i struktura checklisty według typu wniosku.",
    "Основания подачи": "Podstawy wniosku",
    "Список submission types, статусы и локализованные названия в рабочем интерфейсе.": "Lista typów wniosków, statusy i zlokalizowane nazwy w interfejsie roboczym.",
    "Цены и услуги": "Ceny i usługi",
    "Рабочий прайс без Django admin.": "Roboczy cennik bez Django admin.",
    "Записей:": "Wpisów:",
    "Сумма прайса:": "Suma cennika:",
    "Сотрудники": "Pracownicy",
    "Управление staff-аккаунтами, доступом и рабочими ролями.": "Zarządzanie kontami personelu, dostępem i rolami.",
    "Роли": "Role",
    "Система": "System",
    "Техническое состояние, runtime checks и health dashboard.": "Stan techniczny, sprawdzanie środowiska uruchomieniowego i panel zdrowia.",
    "Метрики": "Metryki",
    "Быстрый переход к аналитике и воронке.": "Szybkie przejście do analityki i lejka.",
    "Журналы системы": "Dzienniki systemowe",
    "Просмотр отправленных писем и действий сотрудников (логи аудита).": "Przeglądanie wysłanych e-maili i działań personelu (dzienniki audytu).",
    "Создать новое основание": "Utwórz nowy typ wniosku",
    "Название (внутреннее)": "Nazwa (wewnętrzna)",
    "Статус": "Status",
    "Создать": "Utwórz",
    "Существующие основания": "Istniejące typy wniosków",
    "Слаг": "Slug",
    "Действия": "Działania",
    "Сохранить": "Zapisz",
    "Удалить это основание?": "Usunąć ten typ wniosku?",
    "Удалить": "Usuń",
    "Нет добавленных оснований.": "Brak dodanych typów wniosków.",
    "Управление ценами на услуги.": "Zarządzanie cenami usług.",
    "Описание": "Opis",
    "Цена PLN": "Cena PLN",
    "Сохранить изменения": "Zapisz zmiany",
    "Active cases": "Aktywne sprawy",
    "OCR awaiting review": "OCR czeka na weryfikację",
    "No documents awaiting OCR": "Brak dokumentów oczekujących na OCR",
    "Documents awaiting verification": "Dokumenty oczekują na weryfikację",
    "Missing documents": "Brakujące dokumenty",
    "Expired documents": "Wygasłe dokumenty",
    "No expired documents": "Brak wygasłych dokumentów",
    "Upcoming fingerprints": "Nadchodzące odciski palców",
    "Waiting after fingerprints": "Oczekiwanie po odciskach",
    "Decisions": "Decyzje",
    "Active reminders": "Aktywne przypomnienia",
    "No active reminders": "Brak aktywnych przypomnień",
}

ru_dict = {
    "Active cases": "Активные дела",
    "OCR awaiting review": "OCR ожидает проверки",
    "No documents awaiting OCR": "Нет документов, ожидающих OCR",
    "Documents awaiting verification": "Документы ожидают проверки",
    "Missing documents": "Недостающие документы",
    "Expired documents": "Истекшие документы",
    "No expired documents": "Нет истекших документов",
    "Upcoming fingerprints": "Предстоящие отпечатки",
    "Waiting after fingerprints": "Ожидание после отпечатков",
    "Decisions": "Децизии",
    "Active reminders": "Активные напоминания",
    "No active reminders": "Нет активных напоминаний",
}

def patch_po(lang, mapping):
    po = polib.pofile(f'locale/{lang}/LC_MESSAGES/django.po')
    changed = 0
    for entry in po:
        if entry.msgid in mapping:
            entry.msgstr = mapping[entry.msgid]
            changed += 1
            if 'fuzzy' in entry.flags:
                entry.flags.remove('fuzzy')
    po.save()
    print(f"Updated {changed} entries in {lang}")

patch_po('en', en_dict)
patch_po('pl', pl_dict)
patch_po('ru', ru_dict)
