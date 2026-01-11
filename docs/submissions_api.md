[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Submission & Document API

Below are request examples for working with the submission module's REST endpoints. All requests require an authorized staff member and a standard CSRF token if performed from a browser.

## Submissions

### List and Create
`GET /submissions/api/submissions/` — get all submissions.

`POST /submissions/api/submissions/` — create a new submission.
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"name": "Studies", "status": "draft"}' \
  http://localhost:8000/submissions/api/submissions/
```

### Retrieve and Delete
`GET /submissions/api/submissions/<id>/` — get a submission with documents.

`DELETE /submissions/api/submissions/<id>/` — delete a submission.

## Documents

### List and Create by Submission
`GET /submissions/api/submissions/<submission_id>/documents/`

`POST /submissions/api/submissions/<submission_id>/documents/` — creation (multipart for file upload).
```bash
curl -X POST \
  -b cookies.txt -c cookies.txt \
  -F "title=Passport" \
  -F "status=uploaded" \
  -F "file_path=@/path/to/passport.pdf" \
  http://localhost:8000/submissions/api/submissions/1/documents/
```

### Update and Delete
`PATCH /submissions/api/documents/<id>/` — update document fields.
```bash
curl -X PATCH \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"status": "verified"}' \
  http://localhost:8000/submissions/api/documents/5/
```

`DELETE /submissions/api/documents/<id>/` — delete a document.

---

# Polski <a name="polski"></a>

# API Wniosków i Dokumentów

Poniżej znajdują się przykłady żądań do pracy z punktami końcowymi REST modułu wniosków. Wszystkie żądania wymagają autoryzowanego pracownika i standardowego tokena CSRF, jeśli są wykonywane z przeglądarki.

## Wnioski (Submissions)

### Lista i Tworzenie
`GET /submissions/api/submissions/` — pobierz wszystkie wnioski.

`POST /submissions/api/submissions/` — utwórz nowy wniosek.
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"name": "Studia", "status": "draft"}' \
  http://localhost:8000/submissions/api/submissions/
```

### Pobieranie i Usuwanie
`GET /submissions/api/submissions/<id>/` — pobierz wniosek wraz z dokumentami.

`DELETE /submissions/api/submissions/<id>/` — usuń wniosek.

## Dokumenty

### Lista i Tworzenie (w ramach wniosku)
`GET /submissions/api/submissions/<submission_id>/documents/`

`POST /submissions/api/submissions/<submission_id>/documents/` — tworzenie (multipart dla przesyłania plików).
```bash
curl -X POST \
  -b cookies.txt -c cookies.txt \
  -F "title=Paszport" \
  -F "status=uploaded" \
  -F "file_path=@/path/to/passport.pdf" \
  http://localhost:8000/submissions/api/submissions/1/documents/
```

### Aktualizacja i Usuwanie
`PATCH /submissions/api/documents/<id>/` — aktualizacja pól dokumentu.
```bash
curl -X PATCH \
  -H "Content-Type: application/json" \
  -b cookies.txt -c cookies.txt \
  -d '{"status": "verified"}' \
  http://localhost:8000/submissions/api/documents/5/
```

`DELETE /submissions/api/documents/<id>/` — usuń dokument.

---

# Русский <a name="русский"></a>

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
