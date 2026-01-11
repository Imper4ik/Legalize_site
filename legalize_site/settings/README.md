[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Settings

Project configuration is modular. Django collects these files into a single `settings` object at startup.

## Files

### 1. `base.py`
Common settings for all environments.
*   List of installed apps (`INSTALLED_APPS`).
*   Middleware.
*   Template settings.
*   I18n (Languages, timezones).

### 2. `development.py`
Settings for local development.
*   `DEBUG = True` enabled.
*   SQLite database.
*   Console logging.
*   Email backend that simply prints emails to the console (does not really send them).

### 3. `production.py`
Settings for production (Railway/Heroku).
*   `DEBUG = False`.
*   Postgres database (via `dj-database-url`).
*   Static files configuration (WhiteNoise).
*   Real email sending (SendGrid/Brevo).
*   Sentry (if connected) for error tracking.

## How it works
The `manage.py` file or `DJANGO_SETTINGS_MODULE` environment variable specifies which file to use. Usually defaults to `legalize_site.settings.development`, and set to `legalize_site.settings.production` on the server.

---

# Polski <a name="polski"></a>

# Ustawienia (Settings)

Konfiguracja projektu jest modułowa. Django przy starcie zbiera te pliki w jeden obiekt `settings`.

## Pliki

### 1. `base.py`
Wspólne ustawienia dla wszystkich środowisk.
*   Lista zainstalowanych aplikacji (`INSTALLED_APPS`).
*   Middleware.
*   Ustawienia szablonów.
*   I18n (Języki, strefy czasowe).

### 2. `development.py`
Ustawienia dla lokalnego rozwoju (development).
*   Włączone `DEBUG = True`.
*   Baza danych SQLite.
*   Logowanie do konsoli.
*   Backend e-mail, który po prostu drukuje maile w konsoli (nie wysyła ich naprawdę).

### 3. `production.py`
Ustawienia dla produkcji (Railway/Heroku).
*   `DEBUG = False`.
*   Baza danych Postgres (przez `dj-database-url`).
*   Konfiguracja plików statycznych (WhiteNoise).
*   Rzeczywista wysyłka poczty (SendGrid/Brevo).
*   Sentry (jeśli podłączone) do śledzenia błędów.

## Jak to działa
Plik `manage.py` lub zmienna środowiskowa `DJANGO_SETTINGS_MODULE` wskazuje, którego pliku użyć. Zazwyczaj domyślnie jest to `legalize_site.settings.development`, a na serwerze ustawia się `legalize_site.settings.production`.

---

# Русский <a name="русский"></a>

# Настройки (Settings)

Конфигурация проекта модульная. Django при запуске собирает эти файлы в единый объект `settings`.

## Файлы

### 1. `base.py`
Общие настройки для всех окружений.
*   Список установленных приложений (`INSTALLED_APPS`).
*   Middleware.
*   Настройки шаблонов.
*   I18n (Языки, таймзоны).

### 2. `development.py`
Настройки для локальной разработки.
*   Включен `DEBUG = True`.
*   База данных SQLite.
*   Логирование в консоль.
*   Email-бэкенд, который просто печатает письма в консоль (не отправляет реально).

### 3. `production.py`
Настройки для боя (Railway/Heroku).
*   `DEBUG = False`.
*   База данных Postgres (через `dj-database-url`).
*   Настройка статики (WhiteNoise).
*   Реальная отправка почты (SendGrid/Brevo).
*   Sentry (если подключен) для трекинга ошибок.

## Как это работает
Файл `manage.py` или переменная окружения `DJANGO_SETTINGS_MODULE` указывает, какой файл использовать. Обычно по умолчанию `legalize_site.settings.development`, а на сервере выставляется `legalize_site.settings.production`.
