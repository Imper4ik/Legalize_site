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
- Для production media поддержан S3-compatible backend через `USE_S3_MEDIA_STORAGE=True`.
- Переменные для private media: `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_REGION_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_CUSTOM_DOMAIN`, `PRIVATE_MEDIA_LOCATION`.
- В local/dev без `USE_S3_MEDIA_STORAGE` проект остаётся на файловом `MEDIA_ROOT`.
- Для production используйте `.env.example` как стартовую заготовку и задавайте `SECRET_KEY`, `FERNET_KEYS`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` без небезопасных fallback-значений.
- В production теперь жёстко запрещён `DEBUG=True`, а пустые `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS` считаются ошибкой конфигурации.
- Для трассировки запросов каждый response получает `X-Request-ID`, а логи включают `request_id` и `correlation_id`.
