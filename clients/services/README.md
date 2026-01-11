[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Services

The `clients/services` folder contains utility modules implementing the application's business logic. This keeps `views.py` clean and allows code reuse.

## Component Files

### 1. `calculator.py`
Financial calculator logic.
*   **Functions**: Calculates if the client has enough funds for TRC/Visa, based on living allowance (`LIVING_ALLOWANCE`), housing costs, and family members.
*   **Constants**: `EUR_TO_PLN_RATE` (exchange rate), `LIVING_ALLOWANCE`.

### 2. `notifications.py`
Email notification management.
*   **`send_required_documents_email(client)`**: Sends the client a list of required documents immediately after case creation.
*   **`send_expired_documents_email(client)`**: Notifies if a document is expiring.
*   **`send_payment_reminder_email(payment)`**: Payment reminder.

### 3. `wezwanie_parser.py`
Tool for automating official letter processing (Wezwanie).
*   Parses text from official letters (PDF/Text), extracts requested documents and deadlines.
*   Helps staff quickly generate task lists for clients.

### 4. `responses.py`
Helper utilities for HTTP responses.
*   `apply_no_store(response)`: Adds headers disabling caching (important for pages with PII).

### 5. `pricing.py`
Pricing logic (if separated). Service cost calculation.

---

# Polski <a name="polski"></a>

# Serwisy (Services)

Folder `clients/services` zawiera moduły usługowe realizujące logikę biznesową aplikacji. Pozwala to na utrzymanie czystości w `views.py` i ponowne użycie kodu.

## Pliki Komponentów

### 1. `calculator.py`
Logika kalkulatora finansowego.
*   **Funkcje**: Oblicza, czy klient posiada wystarczającą kwotę na koncie dla Karty Pobytu/Wizy, na podstawie minimum socjalnego (`LIVING_ALLOWANCE`), kosztów mieszkania i liczby członków rodziny.
*   **Stałe**: `EUR_TO_PLN_RATE` (kurs wymiany), `LIVING_ALLOWANCE` (minimum socjalne).

### 2. `notifications.py`
Zarządzanie powiadomieniami e-mail.
*   **`send_required_documents_email(client)`**: Wysyła klientowi listę wymaganych dokumentów natychmiast po utworzeniu sprawy.
*   **`send_expired_documents_email(client)`**: Powiadamia, jeśli ważność dokumentu wygasa.
*   **`send_payment_reminder_email(payment)`**: Przypomnienie o płatności.

### 3. `wezwanie_parser.py`
Narzędzie do automatyzacji przetwarzania listów urzędowych (Wezwanie).
*   Parsuje tekst oficjalnego pisma (PDF/Tekst), wyciąga listę żądanych dokumentów i terminy.
*   Pomaga pracownikowi szybko wygenerować listę zadań dla klienta.

### 4. `responses.py`
Narzędzia pomocnicze dla odpowiedzi HTTP.
*   `apply_no_store(response)`: Dodaje nagłówki uniemożliwiające cache'owanie (ważne dla stron z danymi osobowymi).

### 5. `pricing.py`
Logika wyceny (jeśli wydzielona). Obliczanie kosztów usług.

---

# Русский <a name="русский"></a>

# Сервисы (Services)

Папка `clients/services` содержит служебные модули, реализующие бизнес-логику приложения. Это позволяет держать `views.py` чистыми и переиспользовать код.

## Файлы компонентов

### 1. `calculator.py`
Логика финансового калькулятора.
*   **Функции**: Рассчитывает, достаточна ли сумма на счету клиента для получения ВНЖ/Визы, исходя из прожиточного минимума (`LIVING_ALLOWANCE`), стоимости жилья и количества членов семьи.
*   **Константы**: `EUR_TO_PLN_RATE` (курс обмена), `LIVING_ALLOWANCE` (прожиточный минимум).

### 2. `notifications.py`
Управление email-уведомлениями.
*   **`send_required_documents_email(client)`**: Отправляет клиенту список документов, которые ему нужно собрать, сразу после создания дела.
*   **`send_expired_documents_email(client)`**: Уведомляет, если срок действия документа истекает.
*   **`send_payment_reminder_email(payment)`**: Напоминание об оплате.

### 3. `wezwanie_parser.py`
Инструмент для автоматизации обработки писем от ужонда (Wezwanie).
*   Парсит текст официального письма (PDF/Text), извлекает список затребованных документов и сроки донесения.
*   Помогает сотруднику быстро сформировать список задач для клиента.

### 4. `responses.py`
Вспомогательные утилиты для HTTP ответов.
*   `apply_no_store(response)`: Добавляет заголовки, запрещающие кеширование (важно для страниц с персональными данными).

### 5. `pricing.py`
Логика ценообразования (если вынесена отдельно). Расчет стоимости услуг.
