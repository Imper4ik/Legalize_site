[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Template Tags

The `clients/templatetags` folder contains custom extensions for the Django template engine.

## Files

### 1. `client_filters.py` (or `formatting.py`)
Filters for displaying client data.
*   Phone number formatting.
*   Beautiful status display (color coding for `new`, `approved`, `rejected`).
*   Masking sensitive data in the interface.

### 2. `form_filters.py`
Improving form display (Bootstrap/Tailwind).
*   `|add_class:"form-control"`: Adds CSS classes to form fields directly in the template.
*   `|as_crispy_field`: If Crispy Forms is used.

### 3. `document_tags.py`
Helpers for working with documents.
*   Checking for the existence of a specific document type.
*   Generating download links.

---

# Polski <a name="polski"></a>

# Tagi Szablonów (Template Tags)

Folder `clients/templatetags` zawiera niestandardowe rozszerzenia silnika szablonów Django.

## Pliki

### 1. `client_filters.py` (lub `formatting.py`)
Filtry do wyświetlania danych klienta.
*   Formatowanie numerów telefonów.
*   Ładne wyświetlanie statusów (kodowanie kolorami dla `new`, `approved`, `rejected`).
*   Maskowanie wrażliwych danych w interfejsie.

### 2. `form_filters.py`
Ulepszanie wyświetlania formularzy (Bootstrap/Tailwind).
*   `|add_class:"form-control"`: Dodaje klasy CSS do pól formularza bezpośrednio w szablonie.
*   `|as_crispy_field`: Jeśli używane są Crispy Forms.

### 3. `document_tags.py`
Pomocnicy do pracy z dokumentami.
*   Sprawdzanie istnienia określonego typu dokumentu.
*   Generowanie linków do pobierania.

---

# Русский <a name="русский"></a>

# Шаблонные Теги (Template Tags)

Папка `clients/templatetags` содержит пользовательские расширения для шаблонизатора Django.

## Файлы

### 1. `client_filters.py` (или `formatting.py`)
Фильтры для отображения данных клиента.
*   Форматирование номеров телефонов.
*   Красивый вывод статусов (цветовое кодирование для `new`, `approved`, `rejected`).
*   Маскировка чувствительных данных в интерфейсе.

### 2. `form_filters.py`
Улучшение отображения форм (Bootstrap/Tailwind).
*   `|add_class:"form-control"`: Добавляет CSS классы к полям формы прямо в шаблоне.
*   `|as_crispy_field`: Если используется Crispy Forms.

### 3. `document_tags.py`
Хелперы для работы с документами.
*   Проверка наличия документа определенного типа.
*   Генерация ссылок на скачивание.
