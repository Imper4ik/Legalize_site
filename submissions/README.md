# submissions

## Назначение
Приложение для управления основаниями/типами подач (`Submission`) и связанными документами-шаблонами.

## Функционал
- CRUD для оснований подачи.
- CRUD для документов в рамках выбранного основания.
- Быстрые операции create/update/delete.
- JSON API для оснований и документов.

## Структура
- `models.py` — модели `Submission` и `Document`.
- `views/submissions.py` — web-интерфейс по основаниям.
- `views/documents.py` — web-интерфейс по документам.
- `views/api.py` — API-эндпоинты.
- `forms.py` — формы и валидация.
- `templates/submissions/` — SSR-шаблоны.
- `urls.py` — маршруты web + api.
