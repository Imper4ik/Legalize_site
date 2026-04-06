# legalize_site/templates

## Назначение
Глобальные шаблоны проекта на уровне `legalize_site`.

## Состав
- `base.html` — базовый layout.
- `account/*` и `socialaccount/*` — переопределения шаблонов `django-allauth`.
- `includes/theme_toggle.html` — общий фрагмент переключателя темы.

## Применение
Эти шаблоны используются как проектные overrides и дополняют/перекрывают шаблоны приложений.
