# Submission & Document API

Ниже приведены примеры запросов для работы с REST эндпоинтами модуля оснований подачи. Все запросы требуют авторизованного сотрудника и стандартный CSRF-токен, если выполняются из браузера.

## Основания подачи

### Список и создание
`GET /submissions/api/submissions/` — получить все основания.

`POST /submissions/api/submissions/` — создать новое основание.
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"name": "Учёба", "status": "draft"}' \
  http://localhost:8000/submissions/api/submissions/
```

### Получение и удаление
`GET /submissions/api/submissions/<id>/` — получить основание с документами.

`DELETE /submissions/api/submissions/<id>/` — удалить основание.

## Документы

### Список и создание по основанию
`GET /submissions/api/submissions/<submission_id>/documents/`

`POST /submissions/api/submissions/<submission_id>/documents/` — создание (multipart для загрузки файла).
```bash
curl -X POST \
  -b cookies.txt -c cookies.txt \
  -F "title=Загранпаспорт" \
  -F "status=uploaded" \
  -F "file_path=@/path/to/passport.pdf" \
  http://localhost:8000/submissions/api/submissions/1/documents/
```

### Обновление и удаление
`PATCH /submissions/api/documents/<id>/` — обновить поля документа.
```bash
curl -X PATCH \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"status": "verified"}' \
  http://localhost:8000/submissions/api/documents/5/
```

`DELETE /submissions/api/documents/<id>/` — удалить документ.
