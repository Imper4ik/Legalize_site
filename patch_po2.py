import polib
import json

en_dict = {
    "Status i kluczowe dane / Статус и ключевые данные": "Status and key data",
    "Cel złożenia wniosku / Цель": "Application purpose",
    "Podstawa pobytu i ważność / Основание и срок": "Basis of stay and validity",
    "Единая точка управления печатными шаблонами и значениями по умолчанию.": "Single point of management for printable templates and default values.",
    "Общие значения базы: контакты, адрес офиса, pełnomocnik и значения для Mazowiecki.": "General database values: contacts, office address, proxy and values for Mazowiecki.",
    "Печать и шаблонные значения для Mazowiecki Urząd Wojewódzki.": "Print and template values for Mazowiecki Urząd Wojewódzki.",
    "Следующий кандидат на вынесение общих шаблонных блоков из HTML в настройки базы.": "Next candidate for extracting common template blocks from HTML to database settings.",
    "Сейчас в системе уже есть печатные шаблоны `mazowiecki_application` и `acceleration_request`.": "Currently, the system already has printable templates `mazowiecki_application` and `acceleration_request`.",
    "Вложения, введённые здесь, могут остаться произвольными. После подтверждения система автоматически сопоставит известные пункты чеклиста и отметит их как поданные для этого клиента.": "Attachments entered here can remain arbitrary. After confirmation, the system will automatically match known checklist items and mark them as submitted for this client.",
    "Warszawa, data/date/дата": "Warsaw, date",
    "(ID wniosku w MOS / Request ID form MOS / ID заявки в MOS)": "(Request ID in MOS)",
    "(ID wniosku w InPOL / Request ID form InPOL / ID заявки в InPOL)": "(Request ID in InPOL)",
    "(data złożenia wniosku / date of application / дата подання заяви)": "(Date of application)",
    "(Imię i nazwisko / name and surname / Ім'я та прізвище)": "(Name and surname)",
    "(data urodzenia / date of birth / дата народження)": "(Date of birth)",
    "(obywatelstwo / citizenship / громадянство)": "(Citizenship)",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( количество):": "Mark - Attachments (number):",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( кількість):": "Mark - Attachments (number):",
    "тип проблемы": "type of problem",
    "Риски: %(count)s тип проблемы": "Risks: %(count)s type of problem",
    "Повтор": "Repeat",
    "Флаги": "Flags",
    "Введите электронную почту, привязанную к аккаунту, и мы отправим инструкции.": "Enter the email associated with your account, and we will send instructions.",
    "Проверьте вашу электронную почту. Если письма нет, загляните в папку «Спам» или запросите инструкцию повторно через несколько минут.": "Check your email. If there is no letter, check the Spam folder or request instructions again in a few minutes."
}

pl_dict = {
    "Status i kluczowe dane / Статус и ключевые данные": "Status i kluczowe dane",
    "Cel złożenia wniosku / Цель": "Cel złożenia wniosku",
    "Podstawa pobytu i ważność / Основание и срок": "Podstawa pobytu i ważność",
    "Единая точка управления печатными шаблонами и значениями по умолчанию.": "Pojedynczy punkt zarządzania szablonami do druku i wartościami domyślnymi.",
    "Общие значения базы: контакты, адрес офиса, pełnomocnik и значения для Mazowiecki.": "Ogólne wartości bazy: kontakty, adres biura, pełnomocnik i wartości dla Mazowieckiego.",
    "Печать и шаблонные значения для Mazowiecki Urząd Wojewódzki.": "Wydruk i wartości szablonów dla Mazowieckiego Urzędu Wojewódzkiego.",
    "Следующий кандидат на вынесение общих шаблонных блоков из HTML в настройки базы.": "Kolejny kandydat do przeniesienia ogólnych bloków szablonów z HTML do ustawień bazy.",
    "Сейчас в системе уже есть печатные шаблоны `mazowiecki_application` и `acceleration_request`.": "Obecnie system posiada już szablony do druku `mazowiecki_application` i `acceleration_request`.",
    "Вложения, введённые здесь, могут остаться произвольными. После подтверждения система автоматически сопоставит известные пункты чеклиста и отметит их как поданные для этого клиента.": "Załączniki wpisane tutaj mogą pozostać dowolne. Po potwierdzeniu system automatycznie dopasuje znane pozycje z listy kontrolnej i oznaczy je jako przesłane dla tego klienta.",
    "Warszawa, data/date/дата": "Warszawa, data",
    "(ID wniosku w MOS / Request ID form MOS / ID заявки в MOS)": "(ID wniosku w MOS)",
    "(ID wniosku w InPOL / Request ID form InPOL / ID заявки в InPOL)": "(ID wniosku w InPOL)",
    "(data złożenia wniosku / date of application / дата подання заяви)": "(data złożenia wniosku)",
    "(Imię i nazwisko / name and surname / Ім'я та прізвище)": "(Imię i nazwisko)",
    "(data urodzenia / date of birth / дата народження)": "(data urodzenia)",
    "(obywatelstwo / citizenship / громадянство)": "(obywatelstwo)",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( количество):": "Zaznacz - załączniki (ilość):",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( кількість):": "Zaznacz - załączniki (ilość):",
    "тип проблемы": "typ problemu",
    "Риски: %(count)s тип проблемы": "Ryzyka: %(count)s typ problemu",
    "Повтор": "Powtórz",
    "Флаги": "Flagi",
    "Введите электронную почту, привязанную к аккаунту, и мы отправим инструкции.": "Wprowadź adres e-mail powiązany z kontem, a my wyślemy instrukcje.",
    "Проверьте вашу электронную почту. Если письма нет, загляните в папку «Спам» или запросите инструкцию повторно через несколько минут.": "Sprawdź pocztę e-mail. Jeśli nie ma wiadomości, sprawdź folder Spam lub poproś o instrukcję ponownie za kilka minut."
}

ru_dict = {
    "Status i kluczowe dane / Статус и ключевые данные": "Статус и ключевые данные",
    "Cel złożenia wniosku / Цель": "Цель",
    "Podstawa pobytu i ważność / Основание и срок": "Основание и срок",
    "Warszawa, data/date/дата": "Варшава, дата",
    "(ID wniosku w MOS / Request ID form MOS / ID заявки в MOS)": "(ID заявки в MOS)",
    "(ID wniosku w InPOL / Request ID form InPOL / ID заявки в InPOL)": "(ID заявки в InPOL)",
    "(data złożenia wniosku / date of application / дата подання заяви)": "(дата подачи заявления)",
    "(Imię i nazwisko / name and surname / Ім'я та прізвище)": "(Имя и фамилия)",
    "(data urodzenia / date of birth / дата народження)": "(дата рождения)",
    "(obywatelstwo / citizenship / громадянство)": "(гражданство)",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( количество):": "Отметить - вложения (количество):",
    "Zaznacz/mark/ знак - załączniki (ilość)/Attachments (number)/ Додані документи ( кількість):": "Отметить - вложения (количество):"
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
