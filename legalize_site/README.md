[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Project Configuration (Legalize Site)

This folder contains Django settings, URL configuration, and system checks.

## Structure

### 1. Settings (`settings/`)
Settings are split into modules instead of one large `settings.py`:
*   `base.py`: Base settings for all environments (apps, middleware).
*   `clients.py`, `documents.py`, `payments.py`: Likely specific settings for corresponding modules.

### 2. Checks (`checks.py`)
File contains custom `System Checks` run at Django startup.
*   **`email_configuration_check`**: Validates if email is correctly configured for production.
    *   If `SendGrid` or `Brevo` is used, checks for API keys in environment variables.
    *   Warns if the console backend is enabled (emails won't be sent) or if the placeholder domain `yourdomain.tld` is used.

### 3. Routing (`urls.py`)
Main URL file.
*   Connects admin panel (`/admin/`).
*   Includes `clients` and `submissions` app paths.
*   Handles redirection from the homepage (`dashboard_redirect_view`): staff go to client list, others to login.

### 4. Utilities
*   `mail.py`: Custom backends or utilities for sending mail (e.g., `SafeSMTPEmailBackend`).

---

# Polski <a name="polski"></a>

# Konfiguracja Projektu (Legalize Site)

Ten folder zawiera ustawienia Django, konfigurację adresów URL i testy systemowe.

## Struktura

### 1. Ustawienia (`settings/`)
Ustawienia są podzielone na moduły zamiast jednego dużego pliku `settings.py`:
*   `base.py`: Podstawowe ustawienia dla wszystkich środowisk (aplikacje, middleware).
*   `clients.py`, `documents.py`, `payments.py`: Prawdopodobnie specyficzne ustawienia dla odpowiednich modułów.

### 2. Testy (`checks.py`)
Plik zawiera niestandardowe `System Checks` uruchamiane przy starcie Django.
*   **`email_configuration_check`**: Sprawdza, czy poczta jest poprawnie skonfigurowana dla produkcji.
    *   Jeśli używany jest `SendGrid` lub `Brevo`, sprawdza obecność kluczy API w zmiennych środowiskowych.
    *   Ostrzega, jeśli włączony jest backend konsolowy (maile nie będą wysyłane) lub używana jest domena zastępcza `yourdomain.tld`.

### 3. Routing (`urls.py`)
Główny plik URL.
*   Podłącza panel administratora (`/admin/`).
*   Dołącza ścieżki aplikacji `clients` i `submissions`.
*   Obsługuje przekierowanie ze strony głównej (`dashboard_redirect_view`): pracownicy trafiają na listę klientów, inni do logowania.

### 4. Narzędzia
*   `mail.py`: Niestandardowe backendy lub narzędzia do wysyłania poczty (np. `SafeSMTPEmailBackend`).

---

# Русский <a name="русский"></a>

# Конфигурация проекта (Legalize Site)

Эта папка содержит настройки Django, конфигурацию URL и системные проверки.

## Структура

### 1. Настройки (`settings/`)
Настройки разделены на модули вместо одного большого `settings.py`:
*   `base.py`: Базовые настройки для всех окружений (приложения, middleware).
*   `clients.py`, `documents.py`, `payments.py`: Вероятно, специфичные настройки для соответствующих модулей (или просто логическое разделение).

### 2. Проверки (`checks.py`)
Файл содержит пользовательские системные проверки (`System Checks`), которые запускаются при старте Django.
*   **`email_configuration_check`**: Проверяет, корректно ли настроена почта для продакшена.
    *   Если используется `SendGrid` или `Brevo`, проверяет наличие API-ключей в переменных окружения.
    *   Предупреждает, если включен консольный бэкенд (письма не уходят) или используется домен-заглушка `yourdomain.tld`.

### 3. Маршрутизация (`urls.py`)
Главный файл URL.
*   Подключает админку (`/admin/`).
*   Включает пути приложений `clients` и `submissions`.
*   Обрабатывает перенаправление с главной страницы (`dashboard_redirect_view`): сотрудники попадают в список клиентов, остальные — на логин.

### 4. Утилиты
*   `mail.py`: Содержит кастомные бэкенды или утилиты для отправки почты (например, `SafeSMTPEmailBackend`).
