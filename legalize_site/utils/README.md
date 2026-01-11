[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Utilities (Utils)

The `legalize_site/utils` folder contains general helpers used in different parts of the project.

## Modules

### 1. `i18n.py`
Internationalization handling.
*   **Logic**: Helps determine user language, format dates and numbers depending on locale.
*   **Translations**: Contains functions for forcing language selection when generating documents (e.g., generating a document in Polish even if the admin is using the Russian interface).

### 2. `logging.py`
Logging configuration.
*   Log formatters.
*   Filters to prevent writing sensitive data (PII) to logs (e.g., hiding passwords or passport numbers).

### 3. `http.py`
Network utilities.
*   Functions for working with cookies.
*   IP address handling.

---

# Polski <a name="polski"></a>

# Narzędzia (Utils)

Folder `legalize_site/utils` zawiera ogólne funkcje pomocnicze używane w różnych częściach projektu.

## Moduły

### 1. `i18n.py`
Obsługa internacjonalizacji.
*   **Logika**: Pomaga określić język użytkownika, formatować daty i liczby w zależności od lokalizacji.
*   **Tłumaczenia**: Zawiera funkcje do wymuszania wyboru języka przy generowaniu dokumentów (np. aby dokument generował się po polsku, nawet jeśli administrator korzysta z rosyjskiej wersji interfejsu).

### 2. `logging.py`
Konfiguracja logowania.
*   Formatery logów.
*   Filtry zapobiegające zapisywaniu wrażliwych danych (PII) w logach (np. ukrywanie haseł lub numerów paszportów).

### 3. `http.py`
Narzędzia sieciowe.
*   Funkcje do pracy z plikami cookie.
*   Obsługa adresów IP.

---

# Русский <a name="русский"></a>

# Утилиты (Utils)

Папка `legalize_site/utils` содержит общие хелперы, которые используются в разных частях проекта.

## Модули

### 1. `i18n.py`
Работа с интернационализацией.
*   **Логика**: Помогает определять язык пользователя, форматировать даты и числа в зависимости от локали.
*   **Переводы**: Содержит функции для принудительного выбора языка при генерации документов (например, чтобы документ генерировался на польском, даже если админ сидит в русской версии интерфейса).
*   **Склонения**: Возможно, содержит логику склонения имен (если используется библиотека вроде `pymorphy2` или аналогов).

### 2. `logging.py`
Настройки логирования.
*   Форматтеры для логов.
*   Фильтры, чтобы не писать чувствительные данные (PII) в логи (например, скрывать пароли или номера паспортов).

### 3. `http.py`
Сетевые утилиты.
*   Функции для работы с cookie.
*   Обработка IP-адресов.
