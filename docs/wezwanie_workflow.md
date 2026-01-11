[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Wezwanie and Fingerprint Follow-up Automation

## Objectives
- Inform clients immediately about their fingerprint appointment (date, time, location) and required documents once we receive a *Wezwanie* summons.
- After the fingerprint visit, use the official confirmation document to identify any missing items and send the client a focused reminder.
- Keep a clear audit trail (what was received, when notices were sent, remaining gaps) while minimizing manual data entry.

## Proposed Flow

1.  **Inbound Summons (Wezwanie) Intake**
    - Monitor the shared inbox used for immigration correspondence and auto-file new *Wezwanie* PDFs to the client’s record (matching by case number or email).
    - Parse the summons for: case number, client name, appointment date/time/location, and the checklist of documents requested.
    - Store parsed fields in structured attributes on the `Document`/`Case` model and keep the original PDF attached for reference.

2.  **Appointment Notification to the Client**
    - Immediately send a templated email that includes:
        - Appointment details (date/time/location) pulled from the parsed *Wezwanie*.
        - The list of documents to bring, rendered as a checklist.
        - A link to confirm receipt and ask questions.
    - Record the send status and body snapshot so staff can verify what the client saw.

3.  **Fingerprint Confirmation (Post-visit) Intake**
    - Watch the same inbox for the post-fingerprint confirmation letter that lists delivered vs. outstanding items.
    - Parse the document to extract the visit date and the set of documents still missing.
    - Update the case record: mark the fingerprint step as completed and register outstanding documents with due dates (if provided).

4.  **Automated Missing-document Reminder**
    - Send an email summarizing only the missing items, with clear instructions on how to submit them (upload link or office drop-off) and any deadlines from the letter.
    - If nothing is missing, record a “no outstanding documents” note and skip the reminder.

5.  **Follow-up and Visibility**
    - Schedule a lightweight daily task to re-check outstanding documents and re-send reminders at sensible intervals (e.g., 3 and 7 days before deadline, then weekly) until items are marked received.
    - Surface status in the staff dashboard: latest *Wezwanie* info, fingerprint confirmation, outstanding docs, and email history.

6.  **Error Handling and Safeguards**
    - Flag uncertain matches (e.g., ambiguous case number/name) for manual review instead of auto-sending.
    - Keep all parsed values editable by staff and capture original documents so corrections are easy.
    - Log parsing failures and email delivery issues with alerts to the team channel.

## Why This Is Efficient
- **Single Intake Channel** (shared inbox) removes manual uploads and ensures both summons and post-fingerprint letters are handled the same way.
- **Structured Parsing** keeps critical dates and document lists machine-readable, enabling instant emails and dashboard updates.
- **Targeted Reminders** focus only on missing items, reducing noise for clients and staff.
- **Auditable Trail** links each notification to the source document and stored fields, simplifying compliance and client support.

---

# Polski <a name="polski"></a>

# Automatyzacja Wezwań i Odcisków Palców

## Cele
- Natychmiastowe informowanie klienta o terminie złożenia odcisków palców (data, czas, miejsce) i wymaganych dokumentach po otrzymaniu *Wezwania*.
- Po wizycie (odciski), wykorzystanie oficjalnego potwierdzenia do zidentyfikowania brakujących dokumentów i wysłania klientowi ukierunkowanego przypomnienia.
- Utrzymanie jasnej ścieżki audytu (co otrzymano, kiedy wysłano powiadomienia, pozostałe braki) przy minimalizacji ręcznego wprowadzania danych.

## Proponowany Przepływ

1.  **Przyjmowanie Wezwań**
    - Monitorowanie wspólnej skrzynki odbiorczej używanej do korespondencji urzędowej i automatyczne przypisywanie nowych plików PDF *Wezwań* do rekordu klienta (dopasowanie po numerze sprawy lub e-mailu).
    - Parsowanie wezwania w celu uzyskania: numeru sprawy, imienia i nazwiska klienta, daty/czasu/miejsca wizyty oraz listy żądanych dokumentów.
    - Zapisywanie sparsowanych pól w ustrukturyzowanych atrybutach modelu `Document`/`Case` i zachowanie oryginalnego PDF-a.

2.  **Powiadomienie Klienta o Wizycie**
    - Natychmiastowe wysłanie szablonowego e-maila zawierającego:
        - Szczegóły wizyty (data/czas/miejsce) pobrane ze sparsowanego *Wezwania*.
        - Listę dokumentów do zabrania, w formie listy kontrolnej.
        - Link do potwierdzenia odbioru i zadawania pytań.
    - Zapisanie statusu wysłania i treści wiadomości, aby pracownicy mogli zweryfikować, co zobaczył klient.

3.  **Potwierdzenie Odcisków (Po Wizycie)**
    - Obserwowanie tej samej skrzynki odbiorczej w poszukiwaniu potwierdzenia po wizycie, które wymienia dostarczone vs. brakujące elementy.
    - Parsowanie dokumentu w celu wyodrębnienia daty wizyty i zestawu wciąż brakujących dokumentów.
    - Aktualizacja rekordu sprawy: oznaczenie etapu odcisków jako zakończonego i rejestracja brakujących dokumentów wraz z terminami (jeśli podano).

4.  **Zautomatyzowane Przypomnienie o Brakach**
    - Wysłanie e-maila podsumowującego tylko brakujące elementy, z jasnymi instrukcjami jak je dostarczyć (link do przesyłania lub wizyta w biurze) i ewentualnymi terminami z pisma.
    - Jeśli nic nie brakuje, zapisanie notatki „brak zaległych dokumentów” i pominięcie przypomnienia.

5.  **Follow-up i Widoczność**
    - Zaplanowanie lekkiego codziennego zadania do ponownego sprawdzania brakujących dokumentów i ponownego wysyłania przypomnień w rozsądnych odstępach czasu (np. 3 i 7 dni przed terminem, potem co tydzień), aż elementy zostaną oznaczone jako otrzymane.
    - Wyświetlanie statusu w panelu pracownika: najnowsze info o *Wezwaniu*, potwierdzenie odcisków, zaległe dokumenty i historia e-maili.

6.  **Obsługa Błędów i Zabezpieczenia**
    - Oznaczanie niepewnych dopasowań (np. niejednoznaczny numer sprawy/nazwisko) do ręcznego przeglądu zamiast automatycznej wysyłki.
    - Możliwość edycji wszystkich sparsowanych wartości przez pracowników i zachowanie oryginałów dokumentów dla łatwych korekt.
    - Logowanie błędów parsowania i problemów z dostarczaniem e-maili z alertami na kanał zespołu.

## Dlaczego To Jest Efektywne
- **Jeden Kanał Wlotowy** (wspólna skrzynka) eliminuje ręczne przesyłanie i zapewnia, że zarówno wezwania, jak i listy po odciskach są obsługiwane w ten sam sposób.
- **Strukturalne Parsowanie** utrzymuje krytyczne daty i listy dokumentów w formacie czytelnym dla maszyny, umożliwiając natychmiastowe e-maile i aktualizacje dashboardu.
- **Celowane Przypomnienia** skupiają się tylko na brakujących elementach, redukując szum informacyjny dla klientów i pracowników.
- **Ścieżka Audytu** łączy każde powiadomienie z dokumentem źródłowym i zapisanymi polami, upraszczając zgodność (compliance) i wsparcie klienta.

---

# Русский <a name="русский"></a>

# Автоматизация обработки Wezwanie и отпечатков пальцев

## Цели
- Немедленное информирование клиентов о назначенной встрече на отпечатки (дата, время, место) и необходимых документах после получения *Wezwanie*.
- После визита (сдачи отпечатков) использование официального подтверждения для выявления недостающих документов и отправки клиенту сфокусированного напоминания.
- Поддержание четкого аудиторского следа (что получено, когда отправлены уведомления, оставшиеся пробелы) с минимизацией ручного ввода данных.

## Предлагаемый процесс

1.  **Прием входящих Wezwanie**
    - Мониторинг общей почты, используемой для переписки с ужондом, и авто-сохранение новых PDF *Wezwanie* в карточку клиента (поиск по номеру дела или email).
    - Парсинг вызова для извлечения: номера дела, имени клиента, даты/времени/места встречи и списка запрашиваемых документов.
    - Сохранение извлеченных полей в структурированные атрибуты модели `Document`/`Case` и сохранение оригинального PDF для справки.

2.  **Уведомление клиента о встрече**
    - Немедленная отправка шаблонного письма, включающего:
        - Детали встречи (дата/время/место) из *Wezwanie*.
        - Список документов, которые нужно взять, в виде чеклиста.
        - Ссылку для подтверждения получения и вопросов.
    - Запись статуса отправки и слепка тела письма, чтобы сотрудники могли проверить, что именно увидел клиент.

3.  **Подтверждение отпечатков (после визита)**
    - Отслеживание того же ящика на предмет письма-подтверждения после отпечатков, где перечислены сданные и недостающие документы.
    - Парсинг документа для извлечения даты визита и набора все еще отсутствующих документов.
    - Обновление записи дела: отметка этапа отпечатков как завершенного и регистрация недостающих документов со сроками (если указаны).

4.  **Автоматическое напоминание о недостающих документах**
    - Отправка письма, суммирующего только недостающие позиции, с четкими инструкциями, как их передать (ссылка на загрузку или занос в офис) и сроками из письма.
    - Если ничего не не хватает, запись заметки "нет задолженностей по документам" и пропуск напоминания.

5.  **Контроль и видимость**
    - Планирование легкой ежедневной задачи для перепроверки недостающих документов и переотправки напоминаний с разумными интервалами (например, за 3 и 7 дней до дедлайна, затем еженедельно), пока документы не будут отмечены как полученные.
    - Отображение статуса в панели сотрудника: последнее инфо по *Wezwanie*, подтверждение отпечатков, долги по документам и история писем.

6.  **Обработка ошибок и защита**
    - Пометка неуверенных совпадений (например, неоднозначный номер дела/имя) для ручной проверки вместо авто-отправки.
    - Все спаршенные значения должны быть редактируемыми сотрудниками; оригиналы документов сохраняются для легкой коррекции.
    - Логирование сбоев парсинга и проблем с доставкой писем с алертами в канал команды.

## Почему это эффективно
- **Единый канал приема** (общая почта) убирает ручные загрузки и гарантирует, что и вызовы, и письма после отпечатков обрабатываются одинаково.
- **Структурный парсинг** держит критические даты и списки документов в машиночитаемом виде, позволяя мгновенные рассылки и обновления дашборда.
- **Целевые напоминания** фокусируются только на недостающих позициях, снижая шум для клиентов и сотрудников.
- **Аудиторский след** связывает каждое уведомление с исходным документом и сохраненными полями, упрощая соблюдение процедур и поддержку клиентов.
