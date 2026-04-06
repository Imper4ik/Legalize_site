# legalize_site/settings

## Назначение
Каталог содержит настройки проекта, разделённые по окружениям.

## Файлы
- `base.py` — общие настройки: `INSTALLED_APPS`, `MIDDLEWARE`, шаблоны, i18n, база, email-логика, статика/медиа.
- `development.py` — локальная разработка (`DEBUG=True`, удобные dev-настройки).
- `production.py` — production-профиль (безопасные параметры, доверенные хосты, прокси и т.п.).
- `test.py` — конфигурация для тестов.

## Выбор конфигурации
Используется переменная `DJANGO_SETTINGS_MODULE`, например:
- `legalize_site.settings.development`
- `legalize_site.settings.production`
- `legalize_site.settings.test`

## Практика
- Новые глобальные настройки добавляйте в `base.py`.
- Различия между окружениями держите только в профильных файлах.
