[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Submissions Templates

This folder contains HTML templates for the standard (non-API) views of the `submissions` application.

## Files

### 1. `submission_list.html`
Displays a list of all submissions.
*   Loop through `object_list` (Submissions).
*   Links to details / edit.
*   Button to create a new submission.

### 2. `submission_detail.html`
Detailed view of a submission.
*   Information about the submission (Name, Status).
*   **List of attached documents**: Loop through `object.documents.all`.
*   Forms or modals for adding new documents.

### 3. `submission_form.html`
Form for creating and editing a `Submission` object.
*   Renders `SubmissionForm`.
*   CSRF token protection.

### 4. `document_form.html`
Form for adding or editing a `Document` within a submission.
*   Fields: Title, File input, Status.

---

# Polski <a name="polski"></a>

# Szablony Wniosków (Submissions Templates)

Ten folder zawiera szablony HTML dla standardowych (nie-API) widoków aplikacji `submissions`.

## Pliki

### 1. `submission_list.html`
Wyświetla listę wszystkich wniosków.
*   Pętla przez `object_list` (Wnioski).
*   Linki do szczegółów / edycji.
*   Przycisk do utworzenia nowego wniosku.

### 2. `submission_detail.html`
Szczegółowy widok wniosku.
*   Informacje o wniosku (Nazwa, Status).
*   **Lista załączonych dokumentów**: Pętla przez `object.documents.all`.
*   Formularze lub modale do dodawania nowych dokumentów.

### 3. `submission_form.html`
Formularz do tworzenia i edycji obiektu `Submission`.
*   Renderuje `SubmissionForm`.
*   Ochrona tokenem CSRF.

### 4. `document_form.html`
Formularz do dodawania lub edycji obiektu `Document` w ramach wniosku.
*   Pola: Tytuł, Wybór pliku, Status.

---

# Русский <a name="русский"></a>

# Шаблоны Submissions

Эта папка содержит HTML-шаблоны для стандартных (не-API) представлений приложения `submissions`.

## Файлы

### 1. `submission_list.html`
Отображает список всех оснований.
*   Цикл по `object_list` (Submissions).
*   Ссылки на детали / редактирование.
*   Кнопка создания нового основания.

### 2. `submission_detail.html`
Детальный просмотр основания.
*   Информация об основании (Название, Статус).
*   **Список прикрепленных документов**: Цикл по `object.documents.all`.
*   Формы или модальные окна для добавления новых документов.

### 3. `submission_form.html`
Форма для создания и редактирования объекта `Submission`.
*   Рендерит `SubmissionForm`.
*   Защита CSRF токеном.

### 4. `document_form.html`
Форма для добавления или редактирования объекта `Document` внутри основания.
*   Поля: Название, Загрузка файла, Статус.
