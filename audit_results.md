# Audit Results: Legalize Site

Дата аудита: 2026-05-31  
Проект: `E:\Anigravity\Legalize_site`  
Формат: обзор кода, настроек, миграций, шаблонов, i18n, email/notification flows, бизнес-логики, production scripts, производительности, тестов и зависимостей.

## Краткий вывод

Кодовая база уже содержит несколько сильных защитных решений: production-настройки запрещают `DEBUG=True`, требуют `SECRET_KEY`, `FERNET_KEYS`, `ALLOWED_HOSTS` и `CSRF_TRUSTED_ORIGINS`; onboarding-токены хранятся как HMAC/SHA-256 hash; cron endpoints защищены токеном и POST; пользовательский HTML проходит через `bleach.clean`; прямых небезопасных SQL-запросов в runtime-коде не найдено; `pip-audit` не нашел известных CVE в `requirements.txt`.

Основные риски: локальная база отстает от миграций, расшифровка encrypted fields падает fail-closed без graceful handling на уровне view/service/admin, web-startup запускает background automation loop в каждом web-инстансе, часть staff-поверхности имеет слабую auth/validation модель, а ZUS/reminder логика может пропускать реальные обязательства.

## Таблица проблем

| # | Критичность | Область | Файл | Проблема | Рекомендованное исправление |
|---|---|---|---|---|---|
| 1 | 🔴 High | DB / migrations | [`clients/migrations/0080_alter_client_language.py`](clients/migrations/0080_alter_client_language.py), `manage.py migrate --check` | `showmigrations` показывает `[ ] clients.0080_alter_client_language`, а `migrate --check` завершается с кодом `1`. Это означает, что текущая схема БД не соответствует коду. | Запустить `python manage.py migrate --no-input` для текущей БД. В CI/deploy добавить обязательный `python manage.py migrate --check` перед выпуском. |
| 2 | 🔴 High | Security / encryption | [`fernet_fields/fields.py:42`](fernet_fields/fields.py), [`fernet_fields/fields.py:58`](fernet_fields/fields.py) | `EncryptedTextField` при чтении вызывает `_decrypt(..., fail_closed=True)` и выбрасывает `EncryptedFieldDecryptionError` при `InvalidToken`. Обработчиков этой ошибки вне тестов не найдено. Один поврежденный encrypted value или неверный ключ может валить list/detail/admin/email campaign страницы. | Добавить единый safe-access слой: ловить `EncryptedFieldDecryptionError` в views/services/admin, показывать `[encrypted value unavailable]`, логировать `model`, `pk`, `field` без PII. Добавить тесты на поврежденный ciphertext для client list/detail/admin/log pages. |
| 3 | 🟠 Medium / High | Deployment / jobs | [`start.sh:22`](start.sh), [`start.sh:26`](start.sh) | `ENABLE_BACKGROUND_AUTOMATION_LOOP` по умолчанию `true`, поэтому каждый web-инстанс `gunicorn` стартует собственный `run_background_automation_loop --loop`. При масштабировании web replicas это может дать дублирующую OCR/email/reminder обработку. | Сделать default `false` для web-процесса. Вынести automation loop в отдельный worker/cron service либо добавить распределенный lock на уровне БД/Redis. |
| 4 | 🟠 Medium | Security / access control | [`legalize_site/urls.py:48`](legalize_site/urls.py), [`clients/urls.py:111`](clients/urls.py), [`clients/views/client_crud.py:343`](clients/views/client_crud.py) | `/staff/calculator/` находится в staff namespace, но `calculator_view` не имеет `login_required`, `staff_required_view` или role mixin. Сейчас endpoint публично доступен, если URL известен. | Либо добавить `@staff_required_view`, либо вынести endpoint из `/staff/` и явно считать публичным. Добавить regression test для anonymous access. |
| 5 | 🟠 Medium | Security / auth | [`clients/forms.py:131`](clients/forms.py), [`clients/forms.py:157`](clients/forms.py), [`clients/forms.py:165`](clients/forms.py) | `StaffUserCreateForm` сравнивает `password1/password2`, но не вызывает Django `validate_password`. Через staff UI можно создать слабый пароль, даже если validators настроены. | В `clean()` вызвать `validate_password(password, user)` из `django.contrib.auth.password_validation`. Добавить тесты на слишком короткий/частый пароль. |
| 6 | 🟠 Medium | Business logic / ZUS | [`clients/services/zus.py:65`](clients/services/zus.py), [`clients/services/zus.py:75`](clients/services/zus.py), [`clients/services/zus.py:78`](clients/services/zus.py) | `missing_zus_months()` считает наличие `health_insurance` с `expiry_date` достаточным покрытием; TODO прямо отмечает, что стоит требовать `verified=True`. Непроверенный документ может скрыть отсутствие ZUS RCA. | Фильтровать покрывающие health insurance документы по `verified=True` или отдельному accepted status. Добавить тест: unverified insurance не закрывает missing ZUS month. |
| 7 | 🟠 Medium | Business logic / reminders | [`clients/management/commands/update_reminders.py:248`](clients/management/commands/update_reminders.py), [`clients/management/commands/update_reminders.py:276`](clients/management/commands/update_reminders.py), [`clients/management/commands/update_reminders.py:283`](clients/management/commands/update_reminders.py) | `create_legal_stay_reminders()` проверяет только наличие активного `Reminder` типа `legal_stay`. Если `legal_stay_until` изменился, старый reminder остается с прежней датой и новый/обновленный не создается. | Использовать `update_or_create(client=..., reminder_type="legal_stay", is_active=True, defaults={due_date,title,notes})` или хранить source date в metadata и обновлять при изменении. |
| 8 | 🟠 Medium | Performance | [`legalize_site/context_processors.py:23`](legalize_site/context_processors.py), [`legalize_site/context_processors.py:40`](legalize_site/context_processors.py), [`legalize_site/context_processors.py:51`](legalize_site/context_processors.py) | `onboarding_notifications` выполняет несколько `.count()` с join/filter на каждом authenticated internal request. На больших объемах клиентов это будет заметной ценой для каждой страницы staff UI. | Кэшировать counts на 30-60 секунд per user/role или заменить несколькими counts на один aggregation query. Для OCR counts рассмотреть отдельный lightweight endpoint. |
| 9 | 🟠 Medium | Email / notifications | [`clients/services/email_campaigns.py:89`](clients/services/email_campaigns.py), [`clients/services/email_campaigns.py:123`](clients/services/email_campaigns.py), [`clients/services/email_campaigns.py:125`](clients/services/email_campaigns.py) | Mass email campaign отправляет recipients tight loop через `send_mail` без batch size, delay, retry/backoff или provider throttling. Rate limit есть на создание кампании, но не на фактическую отправку. | Добавить batch processing, configurable pause, retry/backoff и provider-specific limits. Для больших рассылок использовать task queue/worker и сохранять checkpoint. |
| 10 | 🟡 Low / Medium | Performance | [`clients/views/reminders.py:88`](clients/views/reminders.py), [`clients/views/reminders.py:129`](clients/views/reminders.py) | `DocumentReminderListView` вызывает `group["client"].get_document_checklist()` для каждой группы клиентов. Если checklist ходит в документы/requirements, страница напоминаний получает N+1 запросы. | Prefetch related documents/custom requirements в queryset или вынести checklist calculation в bulk service для списка client ids. |
| 11 | 🟡 Low / Medium | Performance / logs | [`clients/views/logs.py:33`](clients/views/logs.py), [`clients/views/logs.py:37`](clients/views/logs.py) | Фильтр email logs использует `sent_at__date__gte/lte`. Такое выражение часто мешает использовать индекс по timestamp и будет хуже масштабироваться. | Перевести фильтр на timezone-aware datetime range: `sent_at__gte=start_dt`, `sent_at__lt=end_dt + 1 day`. |
| 12 | 🟡 Low | Templates / rendering | [`clients/templates/clients/clients_list.html:265`](clients/templates/clients/clients_list.html), [`clients/templates/clients/clients_list.html:270`](clients/templates/clients/clients_list.html), [`clients/templates/clients/clients_list.html:284`](clients/templates/clients/clients_list.html) | Pagination links вручную вставляют `q={{ query }}` без URL encoding. Поиск с `&`, `=` или пробелами ломает query string и сбрасывает фильтры. | Использовать Django `{% querystring page=... %}` или helper для сохранения encoded GET params. |
| 13 | 🟡 Low | Security / CSRF semantics | [`translations/urls.py:11`](translations/urls.py), [`translations/views.py:89`](translations/views.py), [`translations/views.py:90`](translations/views.py) | `toggle_studio_mode` меняет session state через GET. Доступ ограничен translator/admin ролью, но state-changing GET остается плохой CSRF/cache семантикой. | Добавить `@require_POST`, кнопку/форму с CSRF token и тест на запрет GET. |
| 14 | 🟡 Low | i18n | [`templates/base.html`](templates/base.html), [`translations/templates/translations/studio_dashboard.html`](translations/templates/translations/studio_dashboard.html) | Основные `.po/.mo` файлы синхронизированы, `fuzzy` не найдено, но internal Translation Studio содержит hardcoded English UI. Это не ломает клиентские страницы, но оставляет часть staff tooling вне i18n. | Обернуть строки Translation Studio в `{% trans %}` / `{% blocktrans %}` или явно документировать, что tooling только English. |
| 15 | 🟡 Low | Dependencies | [`requirements.txt:32`](requirements.txt) | Проект использует `bleach>=6.0.0`. `pip-audit` CVE не нашел, но сам Bleach помечен upstream как deprecated с 2023-01-23; поддержка в основном security/new Python/major bug fixes. | Не срочно удалять, но изолировать sanitizer API за локальным wrapper и запланировать замену/переоценку. До замены держать актуальный Bleach и иметь XSS regression tests для разрешенных tags. Источники: [PyPI](https://pypi.org/project/bleach/), [GitHub issue #698](https://github.com/mozilla/bleach/issues/698). |
| 16 | 🟡 Low | Environment / production readiness | [`legalize_site/settings/base.py:85`](legalize_site/settings/base.py), [`legalize_site/settings/base.py:87`](legalize_site/settings/base.py), [`legalize_site/checks.py`](legalize_site/checks.py) | `python manage.py check` в текущем локальном окружении дает warnings: console email backend, insecure default `SECRET_KEY`, отсутствует `pg_dump`. В production это частично превращено в hard checks, но локальная/preview среда может работать с degraded email/backups. | Для staging/preview задать real `SECRET_KEY`, email provider credentials и PostgreSQL client tools. В deploy health checklist включить `manage.py check --deploy` с production env vars. |
| 17 | 🟡 Low | Tests / audit confidence | [`pytest.ini:5`](pytest.ini) | Полный `pytest` в рамках аудита не был завершен: в sandbox он падал на permission при создании temp/media/cache, а при escalated запуске ранее ушел в timeout. Текущий `coverage report` не имеет данных. | Починить/задокументировать test runtime на Windows/sandbox: отдельный writable `MEDIA_ROOT`, cache/temp dirs, затем прогонять `python -m pytest -q` в CI. Добавить тесты для пунктов 2-7. |

## Проверенные области без критичных замечаний

| Область | Результат |
|---|---|
| Secrets / env | В `settings/base.py` production без `SECRET_KEY` и `FERNET_KEYS` падает через `ImproperlyConfigured`. Fallback-ключи используются только не-production/build/test сценариями. Реальные Railway/Render env vars из локального репозитория проверить нельзя. |
| Production settings | `production.py` запрещает `DEBUG=True`, требует hosts/origins, включает secure cookies, HSTS и CSP. Отдельное замечание: CSP сейчас допускает `'unsafe-inline'` для script/style; это практично для текущих шаблонов, но стоит ужесточать после инвентаризации inline JS/CSS. |
| SQL injection | В runtime-коде не найдено небезопасных `RawSQL`, `.extra()` или ручных `cursor.execute()` с пользовательским вводом. Найденные `cursor.execute()` находятся в checks/migrations/tests. |
| XSS / HTML | Пользовательские notes проходят через `bleach.clean`; `mark_safe` используется только после sanitization в `sanitize_tags.py`. `|safe` найден в allauth help text templates, не для user-generated content. |
| Static files | Быстрая проверка literal `{% static '...' %}` ссылок в templates не нашла отсутствующих файлов. Build scripts запускают `collectstatic`. |
| i18n catalogs | `#, fuzzy` не найдено в `.po`; `.mo` файлы присутствуют. Быстрая проверка показала одинаковый набор msgids для `ru/pl/en`. |
| Onboarding tokens | Raw token генерируется через `secrets.token_urlsafe(32)`, хранится `token_hash`, есть `expires_at`. Это нормальная модель для magic-link/token onboarding. |
| Email idempotency | `EmailLog` имеет unique constraint на non-empty `idempotency_key`, а notification service строит idempotency keys для повторяемых уведомлений. Это снижает риск дублей в обычных notification flows. |
| Workflow guards | `clients/services/workflow.py` блокирует переходы вперед без обязательных документов/дат и закрытие дела при pending/partial payments. |
| Deploy scripts | `build.sh` компилирует переводы и static; `release.sh` запускает `audit_payment_integrity` и `migrate`; `railway.toml` содержит `releaseCommand = "bash release.sh"`. |
| Dependencies CVE | `python -m pip_audit -r requirements.txt` завершился: `No known vulnerabilities found`. `pip list --outdated --format=json` вернул пустой список в текущем окружении. |

## Приоритетный план исправлений

| Приоритет | Срок | Действия |
|---|---|---|
| P0 | До следующего deploy | Применить `clients.0080_alter_client_language`; убедиться, что release job реально выполняет `release.sh`; зафиксировать `migrate --check` в CI/deploy gate. |
| P0 | До следующего production scale-up | Отключить background automation loop в web startup по умолчанию и вынести его в один worker/cron service либо добавить distributed lock. |
| P1 | 1-2 дня | Добавить graceful handling для `EncryptedFieldDecryptionError` на client/email/admin поверхностях и тест на поврежденный ciphertext. |
| P1 | 1-2 дня | Закрыть `/staff/calculator/` staff-auth декоратором или явно сделать endpoint public вне staff namespace. |
| P1 | 1-2 дня | Включить Django password validators в `StaffUserCreateForm`. |
| P1 | 2-4 дня | Исправить ZUS health insurance coverage: учитывать только verified/accepted документы; добавить regression tests. |
| P1 | 2-4 дня | Исправить legal stay reminders так, чтобы изменение `legal_stay_until` обновляло active reminder. |
| P2 | 1 неделя | Оптимизировать context processor counts, document reminder checklist N+1 и email log date filters. |
| P2 | 1 неделя | Добавить throttling/backoff/checkpointing для mass email campaigns. |
| P3 | Планово | Перевести pagination на encoded query params, сделать Translation Studio toggle POST-only, локализовать internal tooling при необходимости. |
| P3 | Планово | Изолировать `bleach` за wrapper и подготовить стратегию замены; усилить XSS regression tests. |

## Команды проверки

| Команда | Результат |
|---|---|
| `python manage.py check` | Exit `0`, warnings `W002`, `W003`, `W005`. |
| `python manage.py migrate --check` | Exit `1`; есть pending migration `clients.0080_alter_client_language`. |
| `python manage.py showmigrations clients --plan` | Подтвердил `[ ] clients.0080_alter_client_language`. |
| `python -m pip_audit -r requirements.txt` | Exit `0`; `No known vulnerabilities found`. |
| `python -m pip list --outdated --format=json` | Exit `0`; `[]`. |
| Literal static template scan | Missing static refs не найдены. |
| `rg` по SQL/XSS patterns | Runtime unsafe SQL не найден; user-generated HTML sanitization идет через Bleach. |
| `python -m pytest -q` | Полный прогон не завершен в рамках аудита: sandbox permission issue / escalated timeout. |

