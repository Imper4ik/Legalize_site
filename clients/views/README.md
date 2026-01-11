[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Views

The `clients/views` folder contains request handling logic. Instead of one large file, views are separated by purpose.

## Structure

### 1. `base.py`
Base classes and mixins.
*   **`StaffRequiredMixin`**: Restricts view access to staff only (is_staff=True).
*   **`staff_required_view`**: Decorator for function views with the same purpose.

### 2. `clients.py`
Main CRUD (Create, Read, Update, Delete) for clients.
*   `ClientListView`: List of all clients with filtering and search.
*   `ClientDetailView`: Main client card. Assembles context from payments, documents, and reminders.
*   `ClientCreateView` / `ClientUpdateView`: Client addition/editing forms.

### 3. `documents.py`
Document management.
*   File upload, deletion, document status changes.
*   Printable form generation logic (via `ClientDocumentPrintView` in `clients.py` or here if separated).

### 4. `payments.py`
Financial management.
*   Invoice creation (`PaymentCreateView`).
*   Marking payments as "Paid".

### 5. `reminders.py`
Reminder system.
*   Managing `Reminder` entities (creation, deletion, marking as done).

---

# Polski <a name="polski"></a>

# Widoki (Views)

Folder `clients/views` zawiera logikę obsługi żądań. Zamiast jednego dużego pliku, widoki są podzielone według przeznaczenia.

## Struktura

### 1. `base.py`
Klasy bazowe i domieszki (mixins).
*   **`StaffRequiredMixin`**: Ogranicza dostęp do widoku tylko dla pracowników (is_staff=True).
*   **`staff_required_view`**: Dekorator dla widoków funkcyjnych w tym samym celu.

### 2. `clients.py`
Główny CRUD (Create, Read, Update, Delete) dla klientów.
*   `ClientListView`: Lista wszystkich klientów z filtrowaniem i wyszukiwaniem.
*   `ClientDetailView`: Główna karta klienta. Zbiera kontekst z płatności, dokumentów i przypomnień.
*   `ClientCreateView` / `ClientUpdateView`: Formularze dodawania/edycji klienta.

### 3. `documents.py`
Zarządzanie dokumentami.
*   Przesyłanie plików, usuwanie, zmiana statusów dokumentów.
*   Logika generowania formularzy do druku (przez `ClientDocumentPrintView` w `clients.py` lub tutaj).

### 4. `payments.py`
Zarządzanie finansami.
*   Tworzenie rachunków (`PaymentCreateView`).
*   Oznaczanie płatności jako "Opłacone".

### 5. `reminders.py`
System przypomnień.
*   Zarządzanie encjami `Reminder` (tworzenie, usuwanie, oznaczanie jako wykonane).

---

# Русский <a name="русский"></a>

# Представления (Views)

Папка `clients/views` содержит логику обработки запросов. Вместо одного большого файла, views разделены по смыслу.

## Структура

### 1. `base.py`
Базовые классы и миксины.
*   **`StaffRequiredMixin`**: Ограничивает доступ к view только для сотрудников (is_staff=True).
*   **`staff_required_view`**: Декоратор для функциональных view с той же целью.

### 2. `clients.py`
Основной CRUD (Create, Read, Update, Delete) для клиентов.
*   `ClientListView`: Список всех клиентов с фильтрацией и поиском.
*   `ClientDetailView`: Главная карточка клиента. Собирает контекст из платежей, документов и напоминаний.
*   `ClientCreateView` / `ClientUpdateView`: Формы добавления/редактирования клиента.

### 3. `documents.py`
Управление документами.
*   Загрузка файлов, удаление, изменение статусов документов.
*   Логика генерации печатных форм (через `ClientDocumentPrintView` в `clients.py` или здесь, если вынесена).

### 4. `payments.py`
Управление финансами.
*   Создание счетов (`PaymentCreateView`).
*   Отметка платежей как "Оплачено".

### 5. `reminders.py`
Система напоминаний.
*   Управление сущностями `Reminder` (создание, удаление, отметка как выполнено).
