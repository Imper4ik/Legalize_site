[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Submissions Application

This application manages submission types (e.g., "Work Residence Permit", "Visa") and their associated document templates.

## Structure and Components

### 1. Models (`models.py`)
*   **`Submission`**: Defines a type of case/submission. Contains `slug` (unique ID), `name`, and `status`.
*   **`Document`**: Represents a document related to a submission. Can be a template or an uploaded file.

### 2. Views and API (`views.py`)
This app utilizes a hybrid approach:
*   **REST API**: `SubmissionApiView`, `DocumentApiView` for JSON responses (useful for frontend interactions or async calls).
*   **Standard Views**: `SubmissionListView`, `SubmissionDetailView` for server-side rendering using templates.

### 3. Forms (`forms.py`)
Django Forms used for validation and HTML rendering:
*   **`SubmissionForm`**: Validates submission name and status.
*   **`DocumentForm`**: Handles file uploads and document metadata.

### 4. URLs (`urls.py`)
Defines routing for both API and standard views. Separation of concerns prevents creating a monolithic `urls.py` in the root.

### 5. Templates (`templates/`)
HTML templates for the standard views.
*   See detailed documentation: [submissions/templates/README.md](templates/README.md)

---

# Polski <a name="polski"></a>

# Aplikacja Wnioski (Submissions)

Ta aplikacja zarządza typami wniosków (np. "Karta Pobytu na pracę", "Wiza") i powiązanymi z nimi szablonami dokumentów.

## Struktura i Komponenty

### 1. Modele (`models.py`)
*   **`Submission`**: Definiuje typ sprawy/wniosku. Zawiera `slug`, `name` i `status`.
*   **`Document`**: Reprezentuje dokument związany z wnioskiem. Może być szablonem lub przesłanym plikiem.

### 2. Widoki i API (`views.py`)
Aplikacja wykorzystuje podejście hybrydowe:
*   **REST API**: `SubmissionApiView`, `DocumentApiView` dla odpowiedzi JSON (przydatne dla frontendu).
*   **Standardowe Widoki**: `SubmissionListView`, `SubmissionDetailView` do renderowania stron po stronie serwera.

### 3. Formularze (`forms.py`)
Klasy Django Forms używane do walidacji i renderowania HTML:
*   **`SubmissionForm`**: Waliduje nazwę i status wniosku.
*   **`DocumentForm`**: Obsługuje przesyłanie plików i metadane dokumentów.

### 4. URL-e (`urls.py`)
Definiuje routing zarówno dla API, jak i standardowych widoków.

### 5. Szablony (`templates/`)
Szablony HTML dla standardowych widoków.
*   Szczegółowa dokumentacja: [submissions/templates/README.md](templates/README.md)

---

# Русский <a name="русский"></a>

# Приложение Submissions (Основания)

Это приложение управляет типами оснований для подачи (например, "Карта побыту по работе", "Виза") и связанными шаблонами документов.

## Структура и компоненты

### 1. Модели (`models.py`)
*   **`Submission`**: Определяет тип дела/основания. Содержит `slug`, `name` и `status`.
*   **`Document`**: Представляет документ, связанный с основанием. Может быть шаблоном или загруженным файлом.

### 2. Views и API (`views.py`)
Приложение использует гибридный подход:
*   **REST API**: `SubmissionApiView`, `DocumentApiView` для JSON-ответов.
*   **Стандартные Views**: `SubmissionListView`, `SubmissionDetailView` для рендеринга страниц на сервере.

### 3. Формы (`forms.py`)
Django Forms для валидации и отрисовки HTML:
*   **`SubmissionForm`**: Валидация названия и статуса.
*   **`DocumentForm`**: Загрузка файлов и метаданных.

### 4. URLs (`urls.py`)
Определяет маршрутизацию как для API, так и для обычных страниц.

### 5. Шаблоны (`templates/`)
HTML-шаблоны для стандартных представлений.
*   Подробная документация: [submissions/templates/README.md](templates/README.md)
