# legalize_site

## Назначение
Папка `legalize_site/` содержит глобальную конфигурацию Django-проекта: настройки окружений, маршрутизацию, системные проверки и общие утилиты.

## Основные модули
- `settings/` — раздельные настройки (`base`, `development`, `production`, `test`).
- `urls.py` — корневые URL, подключение `clients`, `submissions`, `allauth`, `rosetta`, `translations`.
- `checks.py` — кастомные Django system checks (например, проверка email-конфигурации).
- `mail.py` — безопасный SMTP backend/почтовые helpers.
- `cron_views.py` — служебные endpoint'ы, включая backup-trigger.
- `views.py` — глобальные view (например, `healthcheck`).
- `utils/` — общие утилиты (i18n, http, logging).

## Принцип работы
1. Django запускается с `DJANGO_SETTINGS_MODULE` нужного окружения.
2. Базовые настройки берутся из `settings/base.py`, затем дополняются окружением.
3. URL-уровень подключает прикладные модули и i18n-маршруты.
