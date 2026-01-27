# Builder Pattern Implementation

🏗️ **Автоматизированная система создания объектов с использованием паттерна Builder**

## 📁 Структура

```
clients/services/
├── builders/              # Строители для создания объектов
│   ├── __init__.py
│   ├── client_builder.py     # ClientBuilder - создание клиентов
│   └── payment_builder.py    # PaymentBuilder - создание платежей
│
└── orchestrators/         # Высокоуровневые сервисы
    ├── __init__.py
    └── client_service.py     # ClientService - управление клиентами

examples/
└── builder_usage_examples.py  # Примеры использования

clients/tests/
└── test_builders.py          # Тесты
```

---

## 🚀 Быстрый старт

### 1. Создание базового клиента

```python
from clients.services.builders import ClientBuilder

client = (
    ClientBuilder()
    .with_basic_info("Иван", "Петров", "ivan@example.com")
    .with_contact("+48123456789", "Ukraine")
    .with_application(purpose="study")
    .build()
)
```

### 2. Создание клиента с платежом

```python
from decimal import Decimal

client = (
    ClientBuilder()
    .with_basic_info("Мария", "Коваль", "maria@example.com")
    .with_contact("+48987654321", "Ukraine")
    .with_application(purpose="study")
    .with_initial_payment(
        amount=Decimal('1200'),
        amount_paid=Decimal('600')  # Частичная оплата
    )
    .build()
)

# ✅ Клиент создан
# ✅ Платеж создан автоматически
# ✅ Reminder создан автоматически (через signal)
```

### 3. Использование ClientService (упрощенный API)

```python
from clients.services.orchestrators import ClientService

client = ClientService.create_new_client(
    first_name="Анна",
    last_name="Волкова",
    email="anna@example.com",
    phone="+48444555666",
    citizenship="Ukraine",
    application_purpose="study",
    initial_payment_amount=Decimal('1000'),
    # Дополнительные поля
    passport_num="CC1122334",
    language="ru"
)
```

---

## 📖 Документация API

### ClientBuilder

**Методы конфигурации:**

#### `with_basic_info(first_name, last_name, email)`
Установить базовую информацию о клиенте (обязательно).

```python
.with_basic_info("Иван", "Петров", "ivan@example.com")
```

#### `with_contact(phone, citizenship, birth_date=None, employer_phone=None)`
Установить контактные данные (phone и citizenship обязательны).

```python
.with_contact(
    phone="+48123456789",
    citizenship="Ukraine",
    birth_date=date(1995, 5, 15)
)
```

#### `with_passport(passport_num, case_number=None)`
Установить паспортные данные.

```python
.with_passport(
    passport_num="AA1234567",
    case_number="WRO-2024-00123"
)
```

#### `with_application(purpose, submission_date=None, ...)`
Установить информацию о заявке.

```python
.with_application(
    purpose="study",  # 'study', 'work', 'family' или custom slug
    submission_date=date.today(),
    basis_of_stay="Student Visa",
    legal_basis_end_date=date(2025, 12, 31)
)
```

#### `with_initial_payment(amount, service=None, amount_paid=0, ...)`
Добавить начальный платеж.

```python
.with_initial_payment(
    amount=Decimal('1200'),
    service="study_service",  # Если None - определяется по purpose
    amount_paid=Decimal('600'),
    due_date=date(2024, 12, 31)
)
```

#### `with_notification(send_email=True)`
Включить/выключить отправку email с чеклистом документов.

```python
.with_notification(send_email=True)
```

#### `build()`
Создать клиента со всеми связанными объектами.

```python
client = builder.build()  # Возвращает Client
```

---

### PaymentBuilder

**Методы конфигурации:**

#### `for_service(service=None, amount=None, auto_sync_from_purpose=True)`
Установить услугу и сумму.

```python
PaymentBuilder(client)
    .for_service("study_service", amount=Decimal('1000'))
```

Если `service=None` и `auto_sync=True`, service определяется по `client.application_purpose`:
- `study` → `study_service`
- `work` → `work_service`
- `family` → `consultation`

#### `with_partial_payment(amount, payment_date=None, ...)`
Добавить частичную оплату. Статус определяется автоматически:
- `amount >= total_amount` → `'paid'`
- `0 < amount < total_amount` → `'partial'`
- `amount = 0` → `'pending'`

```python
.with_partial_payment(
    amount=Decimal('500'),
    payment_date=date.today(),
    payment_method='card'
)
```

#### `with_due_date(due_date)`
Установить срок оплаты.

```python
.with_due_date(date(2024, 12, 31))
```

#### `as_paid(payment_date=None, payment_method=None)`
Установить статус "оплачен полностью".

```python
.as_paid(
    payment_date=date.today(),
    payment_method='transfer'
)
```

#### `build()`
Создать платеж.

```python
payment = builder.build()  # Возвращает Payment
```

---

### ClientService

**Статические методы:**

#### `create_new_client(...)`
Создать нового клиента с автоматической настройкой всех компонентов.

```python
client = ClientService.create_new_client(
    first_name="Иван",
    last_name="Петров",
    email="ivan@example.com",
    phone="+48123456789",
    citizenship="Ukraine",
    application_purpose="study",
    initial_payment_amount=Decimal('500'),  # Опционально
    send_welcome_email=True,                 # Опционально
    # Дополнительные поля:
    passport_num="AA1234567",
    case_number="WRO-2024-00123",
    language="ru",
    notes="Примечания"
)
```

#### `add_payment_to_client(client, amount, ...)`
Добавить платеж к существующему клиенту.

```python
payment = ClientService.add_payment_to_client(
    client=client,
    amount=Decimal('1000'),
    service="study_service",           # Опционально
    partial_payment=Decimal('500'),    # Опционально
    due_date=date(2024, 12, 31)        # Опционально
)
```

#### `update_application_purpose(client, new_purpose)`
Обновить цель подачи с автоматической синхронизацией платежей.

```python
ClientService.update_application_purpose(client, 'work')
# Signal автоматически обновит service_description для pending платежей
```

#### `check_missing_documents(client)`
Проверить недостающие документы.

```python
missing = ClientService.check_missing_documents(client)
# [{'code': 'passport', 'name': 'Паспорт', 'is_uploaded': False}, ...]
```

#### `check_expiring_documents(client, days_ahead=30)`
Проверить истекающие документы.

```python
expiring = ClientService.check_expiring_documents(client, days_ahead=7)
# [Document, Document, ...]
```

#### `send_missing_documents_reminder(client)`
Отправить напоминание о недостающих документах.

```python
if ClientService.send_missing_documents_reminder(client):
    print("Email отправлен")
```

#### `get_client_summary(client)`
Получить полную сводку по клиенту.

```python
summary = ClientService.get_client_summary(client)
# {
#     'client': Client,
#     'payments': {
#         'total': 3,
#         'total_paid': Decimal('1500'),
#         'total_due': Decimal('500'),
#         'pending': 1,
#         'partial': 1,
#         'paid': 1
#     },
#     'documents': {
#         'total': 5,
#         'verified': 3,
#         'missing': 2,
#         'expiring_soon': 1
#     },
#     'reminders': {
#         'active': 2,
#         'payment_reminders': 1,
#         'document_reminders': 1
#     },
#     'status': {
#         'application_status': 'new',
#         'application_purpose': 'Учёба',
#         'has_pending_tasks': True,
#         'needs_attention': True
#     }
# }
```

---

## 🎯 Примеры использования

### Пример 1: Создание студента

```python
from datetime import date, timedelta
from decimal import Decimal
from clients.services.builders import ClientBuilder

student = (
    ClientBuilder()
    .with_basic_info("Анна", "Иванова", "anna@example.com")
    .with_contact(
        phone="+48123456789",
        citizenship="Ukraine",
        birth_date=date(1998, 3, 15)
    )
    .with_passport(
        passport_num="AA1234567",
        case_number="WRO-2024-00123"
    )
    .with_application(
        purpose="study",
        submission_date=date.today(),
        basis_of_stay="Student Visa D",
        legal_basis_end_date=date(2025, 12, 31)
    )
    .with_fingerprints(
        fingerprints_date=date.today() + timedelta(days=14),
        fingerprints_location="Wrocław, ul. Piłsudskiego 22"
    )
    .with_language("ru")
    .with_notes("Студентка Warsaw University, факультет IT")
    .with_initial_payment(
        amount=Decimal('1200'),
        amount_paid=Decimal('600'),
        payment_method='card',
        due_date=date.today() + timedelta(days=30)
    )
    .with_notification(send_email=True)
    .build()
)

print(f"Создан студент: {student}")
print(f"Платеж: {student.payments.first()}")
print(f"Напоминание: {student.reminders.first()}")
```

### Пример 2: Создание работника

```python
from clients.services.orchestrators import ClientService

worker = ClientService.create_new_client(
    first_name="Олег",
    last_name="Сидоров",
    email="oleg@example.com",
    phone="+48987654321",
    citizenship="Belarus",
    application_purpose="work",
    initial_payment_amount=Decimal('1500'),
    passport_num="BB9876543",
    language="ru",
    notes="Программист, работает в Tech Company"
)
```

### Пример 3: Добавление платежей

```python
from clients.services.builders import PaymentBuilder

# Добавить частичный платеж
payment1 = (
    PaymentBuilder(client)
    .for_service("consultation", amount=Decimal('500'))
    .with_partial_payment(
        amount=Decimal('250'),
        payment_method='cash'
    )
    .build()
)
# Статус автоматически = 'partial'
# Reminder создастся автоматически

# Добавить полностью оплаченный платеж
payment2 = (
    PaymentBuilder(client)
    .for_service("consultation", amount=Decimal('300'))
    .as_paid(
        payment_date=date.today(),
        payment_method='transfer'
    )
    .build()
)
# Статус автоматически = 'paid'
```

### Пример 4: Проверка статуса клиента

```python
summary = ClientService.get_client_summary(client)

print(f"Клиент: {summary['client']}")
print(f"Всего платежей: {summary['payments']['total']}")
print(f"Оплачено: {summary['payments']['total_paid']} zł")
print(f"Осталось: {summary['payments']['total_due']} zł")
print(f"Недостает документов: {summary['documents']['missing']}")
print(f"Активных напоминаний: {summary['reminders']['active']}")
print(f"Требует внимания: {summary['status']['needs_attention']}")
```

---

## ✅ Автоматизация

### Что происходит автоматически:

1. **При создании клиента с платежом:**
   - ✅ Создается клиент
   - ✅ Создается платеж
   - ✅ `service_description` определяется по `application_purpose`
   - ✅ Статус платежа определяется по `amount_paid`
   - ✅ Если статус `'partial'` → создается Reminder (через signal)
   - ✅ Отправляется email с чеклистом (если `send_email=True`)

2. **При изменении `application_purpose`:**
   - ✅ Signal автоматически обновляет `service_description` для pending платежей

3. **При удалении платежа:**
   - ✅ Signal автоматически удаляет связанное напоминание

4. **При загрузке документа:**
   - ✅ Signal автоматически сжимает изображения

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Django тесты
python manage.py test clients.tests.test_builders -v 2

# Или pytest
pytest clients/tests/test_builders.py -v

# Конкретный тест
pytest clients/tests/test_builders.py::ClientBuilderTestCase::test_basic_client_creation -v
```

### Запуск примеров

```bash
# Через Django shell
python manage.py shell

>>> from examples.builder_usage_examples import *
>>> run_all_examples()

# Или напрямую
python manage.py shell < examples/builder_usage_examples.py
```

---

## 🔄 Миграция существующего кода

### Было (старый способ):

```python
# clients/views/clients.py
class ClientCreateView(StaffRequiredMixin, CreateView):
    def form_valid(self, form):
        self.object = form.save()
        send_required_documents_email(self.object)
        messages.success(self.request, "Клиент успешно создан!")
        return super().form_valid(form)
```

### Стало (новый способ):

```python
from clients.services.orchestrators import ClientService

class ClientCreateView(StaffRequiredMixin, CreateView):
    def form_valid(self, form):
        # Используем сервис
        self.object = ClientService.create_new_client(
            first_name=form.cleaned_data['first_name'],
            last_name=form.cleaned_data['last_name'],
            email=form.cleaned_data['email'],
            phone=form.cleaned_data['phone'],
            citizenship=form.cleaned_data['citizenship'],
            application_purpose=form.cleaned_data['application_purpose'],
            # ... остальные поля
        )
        messages.success(self.request, "Клиент успешно создан!")
        return HttpResponseRedirect(self.get_success_url())
```

**Преимущества:**
- ✅ Меньше кода
- ✅ Вся логика в одном месте
- ✅ Легко тестировать
- ✅ Легко переиспользовать

---

## 🎓 Дополнительная информация

### Связь с существующими компонентами

- **Signals**: Builder использует существующие signals для автоматизации
- **Models**: Builder создает обычные Django модели
- **Services**: Builder использует существующие сервисы (notifications, etc.)
- **Forms**: Builder можно использовать вместе с формами

### Обратная совместимость

Старый код продолжит работать! Builder - это дополнительный слой, который можно использовать опционально.

```python
# Старый способ все еще работает
client = Client.objects.create(
    first_name="Test",
    last_name="User",
    email="test@example.com",
    # ...
)

# Новый способ - опционален
client = ClientBuilder().with_basic_info(...).build()
```

---

## 📝 Лучшие практики

1. **Используйте ClientService для простых случаев:**
   ```python
   ClientService.create_new_client(...)
   ```

2. **Используйте ClientBuilder для сложных случаев:**
   ```python
   ClientBuilder()
       .with_basic_info(...)
       .with_passport(...)
       .with_fingerprints(...)
       .build()
   ```

3. **Валидация данных происходит в `build()`:**
   - Проверяет обязательные поля
   - Проверяет корректность `application_purpose`
   - Выбрасывает `ValueError` при ошибках

4. **Используйте type hints для автодополнения:**
   ```python
   from clients.services.builders import ClientBuilder
   
   builder: ClientBuilder = ClientBuilder()
   # IDE покажет все доступные методы
   ```

---

## 🐛 Troubleshooting

### Ошибка "Не указаны обязательные поля"

```python
# ❌ Неправильно
client = ClientBuilder().build()

# ✅ Правильно
client = (
    ClientBuilder()
    .with_basic_info("Иван", "Петров", "ivan@example.com")  # Обязательно!
    .with_contact("+48123456789", "Ukraine")                # Обязательно!
    .build()
)
```

### Ошибка "Неверная цель подачи"

```python
# ❌ Неправильно
.with_application(purpose="invalid")

# ✅ Правильно
.with_application(purpose="study")  # или 'work', 'family', или существующий slug
```

### Email не отправляется

```python
# Проверьте настройки email в settings.py
# И убедитесь что send_email=True
.with_notification(send_email=True)
```

---

## 📚 Дополнительные ресурсы

- **Design Patterns**: Builder Pattern - https://refactoring.guru/design-patterns/builder
- **Django Best Practices**: Service Layer - https://phalt.github.io/django-api-domains/
- **Testing**: pytest-django - https://pytest-django.readthedocs.io/

---

**Автор:** Antigravity AI  
**Дата:** 2026-01-27  
**Версия:** 1.0.0  
**Branch:** `feature/builder-pattern`
