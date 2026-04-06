# translations

## Назначение
Инструменты редактирования переводов в рантайме (Translation Studio) и обслуживания i18n-пайплайна.

## Функционал
- Dashboard переводов (`/studio/dashboard/`).
- API для чтения/обновления переводов.
- Переключение studio-режима и in-context редактирование.
- Сканирование и оборачивание переводимых фрагментов на странице.

## Состав
- `views.py` — studio dashboard + API endpoints.
- `urls.py` — маршрутизация `/studio/*`.
- `middleware.py` — инъекция/обработка studio-маркеров.
- `apps.py` — интеграция и инициализация поведения переводов.
- `utils.py` — служебные функции для работы с переводами.
- `static/translations/js/translation_overlay.js` — клиентский overlay-редактор.
- `templates/translations/studio_dashboard.html` — интерфейс дашборда.

## Важно
Изменения переводов должны сопровождаться компиляцией `.po -> .mo` (автоматически или через management-команды/утилиты проекта).
