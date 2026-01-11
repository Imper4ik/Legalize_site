[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Management Commands

Custom Django console commands run via `python manage.py <command_name>`.
Located in `clients/management/commands`.

## Available Commands

### 1. `update_reminders`
Command to update reminder statuses and send notifications.
*   **Run**: `python manage.py update_reminders`
*   **How it works**: Checks all active deadlines. If the date has arrived, sends an email to the staff or client and updates the reminder status. Usually set in Cron (task scheduler) to run daily.

### 2. `normalize_document_names`
Utility to standardize document names.
*   **Run**: `python manage.py normalize_document_names`
*   **How it works**: Iterates through the document database and corrects typos or old name formats if the `DocumentRequirement` structure has changed.

---

# Polski <a name="polski"></a>

# Polecenia Zarządzania (Management Commands)

Niestandardowe polecenia konsoli Django uruchamiane przez `python manage.py <command_name>`.
Znajdują się w `clients/management/commands`.

## Dostępne Polecenia

### 1. `update_reminders`
Polecenie do aktualizacji statusów przypomnień i wysyłania powiadomień.
*   **Uruchomienie**: `python manage.py update_reminders`
*   **Jak to działa**: Sprawdza wszystkie aktywne terminy. Jeśli data nadeszła, wysyła e-mail do pracownika lub klienta i aktualizuje status przypomnienia. Zazwyczaj ustawiane w Cronie (harmonogram zadań) do codziennego uruchamiania.

### 2. `normalize_document_names`
Narzędzie do ujednolicania nazw dokumentów.
*   **Uruchomienie**: `python manage.py normalize_document_names`
*   **Jak to działa**: Przechodzi przez bazę dokumentów i poprawia literówki lub stare formaty nazw, jeśli struktura `DocumentRequirement` uległa zmianie.

---

# Русский <a name="русский"></a>

# Команды Управления (Management Commands)

Пользовательские консольные команды Django, запускаемые через `python manage.py <command_name>`.
Находятся в `clients/management/commands`.

## Доступные команды

### 1. `update_reminders`
Команда для обновления статусов напоминаний и отправки уведомлений.
*   **Запуск**: `python manage.py update_reminders`
*   **Как работает**: Проверяет все активные дедлайны. Если дата подошла, отправляет email сотруднику или клиенту и обновляет статус напоминания. Обычно ставится в Cron (планировщик задач) на ежедневный запуск.

### 2. `normalize_document_names`
Утилита для приведения названий документов к единому стандарту.
*   **Запуск**: `python manage.py normalize_document_names`
*   **Как работает**: Проходит по базе документов и исправляет опечатки или старые форматы названий, если структура `DocumentRequirement` изменилась.
