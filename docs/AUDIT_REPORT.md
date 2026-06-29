# Аудит проекта Legalize Site

Дата: 2026-06-29
Ветка: `claude/legalize-site-audit-1ppzyp`
Коммит на момент аудита: `5804020`

> Оговорка об окружении: проект требует **Django 6.0.6 (Python ≥ 3.12)**, а в среде
> аудита доступен **Python 3.11**. Поэтому `manage.py check`, `check --deploy`,
> `makemigrations --check`, миграции, pytest и pip-audit **запустить не удалось** —
> это не баг проекта, а ограничение окружения. Все динамические проверки помечены
> «Не подтверждено: требуется проверка в staging». Статически выполнены: `ruff`
> (чисто), `bandit` (находки только в тестовых файлах). Остальное — доказательный
> разбор кода с указанием файлов и строк.

---

## 1. Executive Summary

**Уровень зрелости: высокий (выше среднего для внутренних CRM).** Это не прототип:
108 миграций, 121 тестовый файл, продуманные production-настройки (HSTS, CSP с
nonce, secure cookies, guard на `DEBUG`), шифрование PII через Fernet, soft-delete,
снапшоты архива для восстановления связей, токены онбординга хранятся только как
HMAC-хеш, cron защищён токеном с constant-time сравнением. Архитектура Client/Case
в основном внедрена и согласована.

**Можно ли работать с реальными клиентами?** — Да, но **после устранения 2–3
ключевых дефектов вокруг сценария «несколько дел у одного клиента»**, который
заявлен как штатный, но именно в нём система ведёт себя некорректно. Для клиента с
одним делом (массовый случай) система работоспособна уже сейчас.

### 5 самых опасных проблем

| # | Проблема | Тип | Severity |
|---|----------|-----|----------|
| 1 | Согласованность Client↔Case защищена **только в `clean()`**; `.save()`/`.objects.create()`/миграции/bulk обходят её. Нет защиты на уровне БД. | Архитектура / data-integrity | High |
| 2 | **Email-уведомления привязаны к Client, а не к Case.** У клиента с 2 активными делами письмо по второму делу подавляется client-level idempotency-ключом (напр. ZUS: `zus_rca_missing:{client.pk}:неделя`). | Подтверждённый баг | High |
| 3 | `create_auto_task` — паттерн **check-then-create без транзакции и без DB-уникальности**: параллельные cron-запуски создают дубли авто-задач. | Race condition | Medium |
| 4 | **Runtime monkeypatch** функции аутентификации (`enable_token_link_access`) + импорт по значению на стартовой странице ⇒ start page и шаги онбординга могут использовать **разные** версии auth (зависит от порядка импорта). | Security / архитектура | Medium |
| 5 | Сохранение нового заявления на карту pobytu (данные + файл подтверждения) **не обёрнуто в `transaction.atomic()`** ⇒ возможен частичный сейв (данные есть, файла нет). | Подтверждённый баг | Medium |

### 5 самых важных улучшений

1. Перенести проверку `case.client_id == client_id` в `save()` (и/или БД-constraint
   через генерируемое поле) для всех «case-consistency» моделей.
2. Сделать idempotency-ключи уведомлений **case-scoped** там, где они сейчас
   client-scoped (ZUS, missing-docs, legal-stay).
3. Обернуть karta-pobytu flow и подобные «данные+файл» операции в `transaction.atomic()`.
4. Добавить DB-уникальность для открытых авто-задач (partial unique index) либо
   `get_or_create` в транзакции, убрав гонку.
5. Убрать monkeypatch: единая `check_client_auth`, вызываемая по module-атрибуту
   везде (или явный параметр `bearer_ok`), плюс удалить мёртвое
   `Case.new_card_application_data`.

### Что уже сделано хорошо

- Production security-baseline (HSTS, CSP+nonce, nosniff, secure/httponly cookies,
  `DEBUG`-guard, проверки SAMESITE=None ⇒ Secure).
- PII шифруется (`EncryptedTextField`/`EncryptedJSONField`/Fernet), есть ротация
  ключей и команды re-encrypt/scrub OCR PII.
- Онбординг-токены: хранится только HMAC-SHA256, raw в БД нет.
- Cron: token-first + constant-time + IP-allowlist, не доверяющий `X-Forwarded-For`.
- Доступ staff — office-wide по дизайну (соответствует §2.1), документы/платежи
  отдаются через `accessible_*_queryset` ⇒ IDOR для staff отсутствует.
- Архив/восстановление через снапшоты (`CaseArchiveSnapshot`) сохраняет прежнее
  состояние связей — продуманно.
- Богатый набор DB-ограничений (22 Check/Unique constraint в моделях клиентов).

---

## 2. Карта проекта

| Компонент | Файлы | Назначение | Состояние | Комментарий |
|-----------|-------|------------|-----------|-------------|
| Backend framework | requirements.txt | Django 6.0.6 | OK | Требует Python ≥3.12 |
| Python | nixpacks.toml / Dockerfile | 3.12 prod | OK | В среде аудита 3.11 |
| Apps | clients, submissions, users, legalize_site, translations | Доменная логика | OK | clients — 46k строк, монолитное ядро |
| Frontend | templates/, static/ | Django templates + Bootstrap, инлайн `<script nonce>` | OK | Есть инлайн-стили (CSP держит `unsafe-inline` для style) |
| DB | dj-database-url, psycopg2 | PostgreSQL | OK | |
| ORM | Django ORM | модели/менеджеры soft-delete | OK | base_manager_name=all_objects |
| Storage | database_media/, django-storages[s3] | Файлы в БД (MVP) или S3 | OK | `USE_DATABASE_MEDIA_STORAGE=True` по умолчанию |
| OCR | pytesseract, pdf2image, opencv | Распознавание документов | OK | Через job-очередь в БД + cron |
| Email | django-anymail[sendgrid,brevo] | Уведомления/кампании | OK | Идемпотентность через EmailLog |
| Cron/jobs | legalize_site/cron_views.py, management/commands | Напоминания, OCR, бэкап | OK | HTTP-эндпойнты + management-команды |
| Hosting | railway.toml, render.yaml, nixpacks.toml | Railway/Render | OK | |
| Docker | Dockerfile, .dockerignore | Контейнеризация | OK | |
| CI/CD | .github/ | — | Не проверено | требует просмотра workflow |
| Env | .env.example, settings/*.py | Конфигурация | OK | Подробный .env.example |
| Encryption | fernet_fields/, clients/security/encrypted.py | Шифрование PII | OK | Ротация ключей |
| AuthN | django-allauth | Аккаунты/логин | OK | |
| AuthZ | clients/services/access.py, roles.py, permissions.py | Роли/доступ | OK (см. §4) | office-wide для staff |
| Logging | legalize_site/utils/logging.py, observability.py | Структурные логи, Sentry | OK | Логи пишут *_type, не PII |
| Backup | legalize_site/backups.py, db_backup.py | pg_dump + шифрование | OK | Хеши/шифрование фиксируются |
| Tests | 121 файл | pytest-django | Не запущены | окружение |

### Текстовая схема потока

```
Клиент / Staff
  → Django template / onboarding-ссылка (raw token) / staff UI
  → URL (clients/urls.py) → view (clients/views/*)
  → permissions: staff_required_view / role_required_view / check_client_auth(token)
  → services (clients/services/*: document_workflow, notifications, cases, tasks, archive)
  → models/ORM (Client, Case, Document, Payment, StaffTask, Reminder, MOSApplicationData)
     ├─ storage: database_media / S3 (FileField)
     ├─ OCR: DocumentProcessingJob → cron process_document_jobs
     ├─ email: notifications._send_email → EmailLog (идемпотентность)
     └─ activity/log: clients/services/activity.log_client_activity
```

- **PII**: `Client` (passport_num, и т.д.), `MOSApplicationData.*_data` (Encrypted),
  `Document.parsed_data` (Encrypted), `Case.authority_case_number` (Encrypted),
  `ClientDigitalAccess.pesel` (Encrypted). Хранятся в БД зашифрованно.
- **Документы**: `Document.file` → `documents/<uuid>.<ext>` (имя пользователя не
  сохраняется), хранилище БД или S3.
- **Проверка ролей**: `clients/services/access.py`, `views/base.py` (декораторы).
- **Создание Case**: `Case.objects.get_or_create_primary_for_client` (signal на
  создание Client), `services/cases.create_case_for_client`.
- **Создание документов**: `services/document_workflow.upload_client_document`.
- **Архив/восстановление**: `services/archive.py`, снапшоты в `Case` модели.
- **Уведомления**: `services/notifications.py`, `management/commands/update_reminders.py`.
- **Cron**: `legalize_site/cron_views.py` (+ `run_background_automation_loop`).
- **Зоны рассинхрона/потери**: §2 (email per-client), karta-pobytu (не atomic),
  дубли авто-задач, дублирующиеся поля Client↔Case.

---

## 3. Матрица требований

| Требование (§2) | Статус | Доказательство | Что исправить |
|-----------------|--------|----------------|---------------|
| Staff — полный доступ ко всем данным | Реализовано | `access.py:59-119` office-wide; `_should_bypass_client_auth` | — |
| Ограничение Admin/Manager на инфраструктуру | Частично/Не подтверждено | роли в `roles.py`, `ADMIN_PANEL_ALLOWED_ROLES`; матрицу не прогнать без запуска | Проверить в staging permission-matrix |
| Массовая проверка документов | Реализовано | `use_cases/documents.verify_all_client_documents` | — (намеренная функция) |
| Новое заявление karta pobytu: статус/номер/дата/коммент/файл | Реализовано неправильно | `onboarding_start_contact.py:246-339` — не atomic; файл привязан к case (OK) | Обернуть в транзакцию |
| Номер дела не теряется | Реализовано | `MOSApplicationData.new_residence_card_case_number` (Encrypted), задача `case_number_missing` | — |
| Файл подтверждения связан с правильным Client+Case | Реализовано | `upload_client_document(..., case=case)` строка 312-320 | — |
| Уведомления привязаны к Case (не только Client) | Реализовано неправильно | `notifications.py` idempotency по `client.pk`; `update_reminders.py:175` | Сделать ключи case-scoped |
| Идемпотентность уведомлений | Частично | EmailLog+ключ есть, но client-scoped | см. выше |
| Авто-проверки после отпечатков/дедлайнов/документов | Реализовано | `update_reminders.create_fingerprints_followup_tasks` (per-case, self-heal) | — (хорошо) |
| Timezone Europe/Warsaw | Не подтверждено | `timezone.localdate()` используется; TIME_ZONE не проверен в base.py | Проверить TIME_ZONE и DST |
| Нет cross-client/cross-case записей | Реализовано неправильно | защита только `clean()`, нет на уровне БД/`save()` | Перенести в save()/DB |

---

## 4. Реестр проблем

> Категории: **BUG** (подтверждённый баг), **RISK**, **DEBT** (техдолг), **ARCH**
> (архитектура), **SEC** (security), **UX**, **MISSING**, **DUP** (лишнее/дубли),
> **PRODUCT** (спорное продуктовое), **OWNER** (решение владельца).

### P-01 — Согласованность Client↔Case только в `clean()` `[ARCH/RISK · High]`
- **Где**: `clients/models/document.py:261-288` (`clean` vs `save`),
  `models/reminder.py:114-190`, `models/task.py:149-181`, `models/onboarding.py`
  (`MOSApplicationData`, `PeselApplication`, `ClientOnboardingSession`),
  `models/document.py:514-540` (`ClientDocumentRequirement`).
- **Доказательство**: во всех этих моделях `clean()` содержит
  `if self.case and self.case.client_id != self.client_id: raise ValidationError`,
  но `save()` выполняет **только** авто-резолв `case` при `case_id is None` и
  **не повторяет** проверку несоответствия. `full_clean()` из `save()` не
  вызывается. Триггеров/`CheckConstraint` на равенство `case.client == document.client`
  нет (`grep` по миграциям — ни одного RunSQL-триггера).
- **Сценарий**: `Document.objects.create(client=A, case=case_of_B)` или
  data-migration/bulk-update создаёт документ клиента A в деле клиента B — БД примет.
- **Последствия**: PII-документ одного клиента попадает в дело другого; нарушается
  главное архитектурное правило §1.
- **Исправление**: добавить проверку соответствия в `save()` (поднимать `ValueError`),
  и/или денормализовать `case_client_id` с `CheckConstraint(case_client_id == client_id)`,
  либо генерируемый столбец + constraint. Нужна миграция.
- **Нужна миграция**: да (если делать на уровне БД).
- *Смягчение*: Django admin сохраняет через ModelForm → `clean()` вызывается, поэтому
  ручной ввод в админке защищён; брешь — прямой ORM/скрипты/миграции.

### P-02 — Email-уведомления client-scoped вместо case-scoped `[BUG · High]`
- **Где**: `clients/services/notifications.py` (idempotency-ключи),
  `clients/management/commands/update_reminders.py:124,175`.
- **Доказательство**:
  - `send_missing_documents_email` ключ `missing_documents:{client.pk}:W{week}`
    (строка 753-756); контекст `_get_missing_documents_context` берёт
    `client.documents` (все дела) и `resolve_single_active_case` (None при 2+ делах).
  - `check_zus_rca_missing_months` итерируется **по делам**, но письмо использует
    `weekly_key = f"zus_rca_missing:{client.pk}:..W{week}"` (update_reminders.py:175).
    У клиента с двумя делами, у обоих нет ZUS, **второе письмо подавляется** тем же
    client-level ключом за ту же неделю.
  - `_get_appointment_context`/`_get_expired_documents_context` через
    `resolve_single_active_case` (cases.py:95-106) **возвращают None при 2+ делах** —
    письма о встрече/просроченных вообще не отправляются мульти-кейс клиенту.
- **Сценарий**: клиент с делами #1 и #2, оба в `waiting_decision`. Письмо по
  недостающим/ZUS уходит один раз и/или агрегирует документы обоих дел; appointment-
  и expired-письма не уходят совсем.
- **Последствия**: клиент не получает уведомления по части дел → пропущенные дедлайны.
- **Исправление**: idempotency-ключи строить по `case.pk`; контексты вычислять
  по делу (фильтровать `client.documents.filter(case=case)`); итерироваться по
  активным делам, а не по клиенту.
- **Нужна миграция**: нет.

### P-03 — Гонка в `create_auto_task` `[RACE/RISK · Medium]`
- **Где**: `clients/services/tasks.py:31-75`; модель `StaffTask` (task.py) без
  уникального ограничения на открытые авто-задачи.
- **Доказательство**: `existing_query.exists()` затем `StaffTask.objects.create(...)`
  без `transaction.atomic()`/`select_for_update`/DB-constraint. Два cron-процесса
  (или cron + ручное действие) проходят `.exists()==False` и оба создают задачу.
- **Сценарий**: `process_document_jobs` и `update_reminders` пересекаются по времени.
- **Последствия**: дубли задач сотрудникам (спам в очереди), искажение метрик.
- **Исправление**: partial `UniqueConstraint(fields=[client,case,task_type],
  condition=Q(status__in=open/in_progress, is_auto_created=True))` + `get_or_create`,
  обработка `IntegrityError`.
- **Нужна миграция**: да.

### P-04 — Monkeypatch аутентификации и расхождение start/шаги `[SEC/ARCH · Medium]`
- **Где**: `clients/views/onboarding_token_access.py` (весь файл),
  `clients/views/__init__.py:16,50`, `clients/views/onboarding_start_contact.py:28,536`.
- **Доказательство**: `enable_token_link_access()` (вызывается в `__init__.py:50`)
  подменяет module-атрибут `onboarding_views.check_client_auth` на
  bearer-версию. Но `onboarding_start_contact.py:28` делает
  `from clients.views.onboarding_views import check_client_auth` — **связывание по
  значению**, происходящее на строке 16 `__init__.py`, т.е. **до** патча (строка 50).
  Поэтому стартовая страница вызывает **оригинальную** `check_client_auth` (требует
  логин/пароль), тогда как шаги (`onboarding_views`, `onboarding_step_return.py:18`,
  через module-атрибут) — **пропатченную** (token-bearer).
- **Сценарий**: клиент по ссылке из письма открывает start page → редирект на
  логин/установку пароля, а внутренние шаги доступны без логина. Поведение auth
  непоследовательно и **зависит от порядка импортов** (хрупко при рефакторинге).
- **Последствия**: непредсказуемый UX; риск, что будущий рефактор молча изменит
  модель доступа на части страниц.
- **Исправление**: убрать monkeypatch. Сделать единую функцию с явным флагом
  (`allow_token_bearer: bool`) или вызывать строго через module-атрибут везде; покрыть
  тестом эквивалентность auth на всех онбординг-вью.
- **Нужна миграция**: нет.

### P-05 — Karta pobytu flow не атомарен `[BUG · Medium]`
- **Где**: `clients/views/onboarding_start_contact.py:285-320`.
- **Доказательство**: `_save_new_card_values(mos_data, values)` (запись MOS) и
  `upload_client_document(...)` (запись Document+файл) идут последовательно **без**
  общей `transaction.atomic()`. Создание авто-задачи между ними.
- **Сценарий**: статус «подано», номер сохранён, но `upload_client_document` падает
  (storage/OCR/валидация на стороне сохранения) → MOS говорит «есть подача», а файла
  подтверждения нет. Либо наоборот при иной последовательности.
- **Последствия**: рассинхрон данных и подтверждающего файла; «висячее» состояние.
- **Исправление**: обернуть весь блок (валидация выполнена ранее — ОК) в
  `transaction.atomic()`; файл сохранять до коммита MOS-статуса или вместе.
- **Нужна миграция**: нет.

### P-06 — Мёртвое/дублирующее поле `Case.new_card_application_data` `[DUP/DEBT · Low]`
- **Где**: `clients/models/case.py:135`.
- **Доказательство**: `grep new_card_application_data` по `*.py` — поле читается/пишется
  **только** в миграции-бэкфилле `0096_*` (строки 157-217). Живой поток использует
  `MOSApplicationData.new_residence_card_*`. Нигде в views/services поле не используется.
- **Последствия**: дублирование источника правды, путаница, лишний шифрованный столбец.
- **Исправление**: подтвердить с владельцем, что миграция-источник больше не нужна,
  затем удалить поле (миграция RemoveField).
- **Нужна миграция**: да.

### P-07 — Дублирование процессных полей Client↔Case `[DEBT/ARCH · Medium]`
- **Где**: `clients/models/client.py:175-192` (`application_purpose`, `basis_of_stay`,
  `status`) дублируют одноимённые поля `Case` (`case.py:106-115`).
- **Доказательство**: `Case.create_from_client` копирует значения из Client; обе
  модели хранят `status`/`application_purpose`/`basis_of_stay`. Для клиента с
  несколькими делами `Client.status` неоднозначен (какое дело он отражает?).
  *Позитив*: процессные поля прошлой модели (`workflow_stage`, `fingerprints_*`,
  `case_number`, `decision_date`, `submission_date`) **уже удалены** из Client
  (в `create_from_client` доступ к ним через `getattr(..., default)`), миграция
  к Case-first почти завершена.
- **Последствия**: рассинхрон Client.status и Case.status; неоднозначность при 2+ делах.
- **Исправление**: определить источник правды (Case), а на Client оставить либо
  вычисляемое свойство, либо явно «последнее/основное дело». Решение владельца (см. Q-2).
- **Нужна миграция**: возможно (если удалять поля).

### P-08 — `display_name` документа делает запрос на объект (N+1) `[PERF · Low]`
- **Где**: `clients/models/document.py:312-334`.
- **Доказательство**: при отсутствии `_preloaded_requirement` свойство дёргает
  `self.client.get_document_requirement_purpose()` и `DocumentRequirement.objects.filter(...)`
  на каждый документ. В списках без префетча — N+1.
- **Последствия**: лишние запросы на страницах со списками документов.
- **Исправление**: префетчить requirement (как уже сделано через `_preloaded_*` в
  части кода) повсеместно; проверить списки.
- **Нужна миграция**: нет. *Не подтверждено количественно: требуется профайл в staging.*

### P-09 — Bandit B608/B108 только в тестах `[INFO · Low]`
- **Где**: `clients/tests/test_encrypted_resilience.py`, `test_services_stage5.py`,
  `legalize_site/tests/test_cron_views.py`.
- **Доказательство**: f-string SQL и `/tmp/...` пути — **в тестовом коде**, prod не
  затронут. Реальной уязвимости нет.
- **Исправление**: можно добавить `# nosec` с пояснением; не приоритет.

### P-10 — Архивные документы недоступны для preview/download `[UX/RISK · Low]`
- **Где**: `clients/views/documents.py:389-424` через
  `accessible_documents_queryset` → `Document.objects` (active-only manager).
- **Доказательство**: дефолтный менеджер исключает soft-deleted; staff не сможет
  открыть файл архивированного документа из обычного маршрута.
- **Последствия**: при разборе спорных кейсов staff не видит файл архивного документа.
- **Исправление**: подтвердить желаемое поведение с владельцем (Q-3); при
  необходимости — отдельный маршрут на `all_objects` для привилегированных ролей.

---

## 5. Замечания по этапам (сводно)

**БД/модели (Этап 2).** Сильная сторона: 22 Check/Unique-ограничения, индексы под
запросы, soft-delete + снапшоты архива, `Case.client` = `PROTECT`. Слабое место —
единый паттерн «проверка только в `clean()`» (P-01) на 6 моделях. Восстановление из
архива спроектировано корректно (снапшот хранит `previous_*` состояние) — потери
связей при restore не выявлено (статически).

**Бизнес-логика/жизненный цикл (Этап 3).** Для одного дела — целостно. Для
нескольких дел одного клиента ломаются именно уведомления (P-02) и неоднозначен
`Client.status` (P-07). DB-напоминания (`create_document/payment/legal_stay_reminders`)
и `fingerprints_followup` задачи — корректно case-scoped (хорошо).

**Security/Privacy (Этап 4).** Хорошо: токены — HMAC-хеш; cron — token+IP; serve
файлов через protected response + `nosniff` + `no-store`; staff-IDOR закрыт queryset-
фильтрами; имена файлов не сохраняются (`document_upload_path`); upload-валидация
(`validate_uploaded_document`). Риски: monkeypatch auth (P-04). Логи пишут `*_type`
и id, не PII (проверено в notifications/cron). HSTS/CSP/cookies — на месте.
*Не подтверждено динамически (требуется staging)*: brute-force/rate-limit на логине,
session fixation, реальные заголовки ответа.

**Архитектура/качество (Этап 5).** `clients` — крупный монолит (46k строк, файлы по
1.6–1.8k строк: `document_workflow.py`, `client.py`). Разнесение на views/services/
use_cases выполнено аккуратно. Дубли: P-06, P-07. Один monkeypatch (P-04). Ruff —
чисто, типизация (`from __future__ import annotations`, `Self`, mypy-конфиг) развита.

**Notifications/Cron/OCR/Dates (Этап 6).** Идемпотентность через `EmailLog` +
`select_for_update` (хорошо), демо/тест-данные не шлются реально. Главный дефект —
client-scoped ключи (P-02). OCR через job-очередь в БД с `reclaim_stale_document_jobs`
(retry/таймаут-реклейм есть). Polish holidays/DST — *не подтверждено*, нужно
проверить `TIME_ZONE` и `workday.py`.

**UI/UX (Этап 7).** Инлайн-стили присутствуют (CSP оставляет `unsafe-inline` для
style — есть план перехода в Report-Only). Karta-pobytu блок локализован (PL/RU). Не
проверено вживую (нет запуска) — *требуется staging*: мобильная адаптивность, empty/
loading/error-состояния, фокус/контраст.

**Performance/DevOps (Этап 8).** select_related/prefetch применяются в `access.py` и
`update_reminders`. Потенциальный N+1 — P-08. Бэкап (`backups.py`, `db_backup`) с
шифрованием и хешами; `test_restore` присутствует. Health-check и observability/Sentry
настроены. Release/start скрипты есть. *Динамику миграций/деплоя проверить в staging.*

---

## 6. Особые зоны (§12) — вердикты

| Зона | Вердикт | Доказательство |
|------|---------|----------------|
| 1. Cross-client/cross-case через ORM | **Подтверждено уязвимо** | P-01: только `clean()`, нет save()/DB |
| 2. Onboarding token: разные auth, monkeypatch, логи | **Подтверждено** (расхождение + monkeypatch); raw-токены не логируются | P-04; токен только в URL, в БД — хеш |
| 3. Reminders на уровне Client; idempotency блокирует 2-е дело | **Подтверждено** | P-02 (особенно ZUS-ключ) |
| 4. Дубли авто-задач при параллельном cron | **Подтверждено** | P-03: нет DB-защиты |
| 5. Karta pobytu: транзакционность/висячий файл | **Подтверждено** (не atomic) | P-05 |
| 6. Старые поля/дубли | **Подтверждено** | P-06 (`Case.new_card_application_data`), P-07 (Client.status/purpose/basis) |

Дополнительно по §12.2: повторное использование/отзыв/срок ссылки — у
`ClientOnboardingSession` есть `expires_at`, `revoked_at`, статусы `expired/revoked`
(модель поддерживает отзыв и срок). Защита от утечки через Referer: `SECURE_REFERRER_POLICY
= strict-origin-when-cross-origin` (prod) — токен в пути URL всё же может попасть в
history/логи прокси (*остаточный риск, требует решения владельца — Q-1*).

---

## 7. Вопросы владельцу продукта (OWNER)

- **Q-1**: Допустимо ли держать raw-токен онбординга в пути URL (history/Referer/
  access-логи), или нужно менять на server-side сессию после первого визита?
- **Q-2**: Источник правды для `status/application_purpose/basis_of_stay` — Case?
  Можно ли удалить дубли с Client (P-07)?
- **Q-3**: Должен ли staff открывать файлы архивных документов из карточки (P-10)?
- **Q-4**: Подтвердить, что миграция-источник `Case.new_card_application_data` (0096)
  больше не нужна и поле можно удалить (P-06).

---

## 8. Что НЕ удалось проверить (нужен staging/production)

`manage.py check`/`--deploy`, `makemigrations --check`, pytest (121 файл),
pip-audit (уязвимости зависимостей), реальные security-заголовки, rate-limit/
brute-force, TIME_ZONE/DST/праздники, N+1 в реальных списках, UX вживую, процесс
деплоя/rollback. Причина: окружение аудита — Python 3.11, проект требует ≥3.12
(Django 6.0). **Это ограничение окружения, не дефект проекта.**
