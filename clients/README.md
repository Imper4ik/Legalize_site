[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Clients Application

The `clients` app is the core of the system and contains all business logic for managing client cases.

## Folder Structure

Below is the complete structure of the application with a description of each folder's purpose:

*   **`views/`**: [Views and Handlers](views/README.md)
    *   Contains web request handling logic. Split into modules (`clients.py`, `documents.py`, `payments.py`) for convenience.
*   **`services/`**: [Business Logic and Services](services/README.md)
    *   Here resides "pure" logic not directly tied to HTTP. Calculator calculations, email sending, file parsing.
*   **`templatetags/`**: [Template Tags](templatetags/README.md)
    *   Custom filters and tags for use in HTML templates (e.g., status formatting or permission checking).
*   **`management/commands/`**: [Admin Commands](management/README.md)
    *   Scripts run via `python manage.py` (e.g., bulk updates or cron tasks).
*   **`migrations/`**: Database migrations (auto-generated Django files).
*   **`templates/`**: HTML page templates.

## Key Files in Root

*   **`models.py`**: Data structure definitions (Client, Document, Payment).
*   **`forms.py`**: Forms for data entry and validation (ClientForm, PaymentForm).
*   **`admin.py`**: Settings for display in the Django admin panel.
*   **`urls.py`**: URL routing within the application.
*   **`signals.py`**: Event handlers (e.g., creating a profile when a user is created).
*   **`constants.py`**: Project constants (e.g., default document lists).

---

# Polski <a name="polski"></a>

# Aplikacja Klienci (Clients)

Aplikacja `clients` jest rdzeniem systemu i zawiera całą logikę biznesową zarządzania sprawami klientów.

## Struktura Folderów

Poniżej znajduje się pełna struktura aplikacji z opisem przeznaczenia każdego folderu:

*   **`views/`**: [Widoki i Obsługa](views/README.md)
    *   Zawiera logikę obsługi żądań internetowych. Podzielona na moduły (`clients.py`, `documents.py`, `payments.py`) dla wygody.
*   **`services/`**: [Logika Biznesowa i Serwisy](services/README.md)
    *   Tutaj znajduje się "czysta" logika, niezwiązana bezpośrednio z HTTP. Obliczenia kalkulatora, wysyłanie e-maili, parsowanie plików.
*   **`templatetags/`**: [Tagi Szablonów](templatetags/README.md)
    *   Niestandardowe filtry i tagi do użycia w szablonach HTML (np. formatowanie statusów czy sprawdzanie uprawnień).
*   **`management/commands/`**: [Polecenia Administratora](management/README.md)
    *   Skrypty uruchamiane przez `python manage.py` (np. masowe aktualizacje lub zadania cron).
*   **`migrations/`**: Migracje bazy danych (automatycznie generowane pliki Django).
*   **`templates/`**: Szablony stron HTML.

## Główne Pliki w Katalogu Głównym

*   **`models.py`**: Definicje struktur danych (Client, Document, Payment).
*   **`forms.py`**: Formularze do wprowadzania i walidacji danych (ClientForm, PaymentForm).
*   **`admin.py`**: Ustawienia wyświetlania w panelu administracyjnym Django.
*   **`urls.py`**: Routing URL wewnątrz aplikacji.
*   **`signals.py`**: Obsługa zdarzeń (np. tworzenie profilu po utworzeniu użytkownika).
*   **`constants.py`**: Stałe projektu (np. domyślne listy dokumentów).

---

# Русский <a name="русский"></a>

# Клиенты (Clients Application)

Приложение `clients` является ядром системы и содержит всю бизнес-логику по управлению делами клиентов.

## Структура Папок

Ниже приведена полная структура приложения с описанием назначения каждой папки:

*   **`views/`**: [Представления и Обработчики](views/README.md)
    *   Содержит логику обработки веб-запросов. Разделена на модули (`clients.py`, `documents.py`, `payments.py`) для удобства.
*   **`services/`**: [Бизнес-логика и Сервисы](services/README.md)
    *   Здесь живет "чистая" логика, не завязанная напрямую на HTTP. Расчеты калькулятора, отправка писем, парсинг файлов.
*   **`templatetags/`**: [Шаблонные Теги](templatetags/README.md)
    *   Кастомные фильтры и теги для использования в HTML-шаблонах (например, форматирование статусов или проверка прав).
*   **`management/commands/`**: [Команды Администратора](management/README.md)
    *   Скрипты для запуска через `python manage.py` (например, массовые обновления или крон-задачи).
*   **`migrations/`**: Миграции базы данных (автогенерируемые файлы Django).
*   **`templates/`**: HTML-шаблоны страниц.

## Основные Файлы в Корне

*   **`models.py`**: Определения структур данных (Client, Document, Payment).
*   **`forms.py`**: Формы для ввода и валидации данных (ClientForm, PaymentForm).
*   **`admin.py`**: Настройки отображения в админ-панели Django.
*   **`urls.py`**: Маршрутизация URL внутри приложения.
*   **`signals.py`**: Обработчики событий (например, создание профиля при создании пользователя).
*   **`constants.py`**: Константы проекта (например, списки документов по умолчанию).
