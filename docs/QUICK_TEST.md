# 🧪 Quick Test Guide - Builder Pattern

## ✅ Как протестировать новую функциональность

### 1. Быстрый тест (5 минут)

```bash
# Запустить Django shell
python manage.py shell
```

```python
# В shell выполнить:
from decimal import Decimal
from clients.services.builders import ClientBuilder

# Создать тестового клиента
client = (
    ClientBuilder()
    .with_basic_info("Test", "User", "test@example.com")
    .with_contact("+48123456789", "Ukraine")
    .with_application(purpose="study")
    .with_initial_payment(amount=Decimal('1000'), amount_paid=Decimal('500'))
    .build()
)

print(f"✅ Клиент создан: {client}")
print(f"   ID: {client.id}")
print(f"   Email: {client.email}")
print(f"   Платежей: {client.payments.count()}")
print(f"   Напоминаний: {client.reminders.count()}")

# Проверка платежа
payment = client.payments.first()
print(f"\n💳 Платеж:")
print(f"   Сумма: {payment.total_amount} zł")
print(f"   Оплачено: {payment.amount_paid} zł")
print(f"   Статус: {payment.get_status_display()}")
print(f"   Услуга: {payment.get_service_description_display()}")

# Проверка напоминания (должно создаться автоматически)
reminder = client.reminders.first()
if reminder:
    print(f"\n🔔 Напоминание:")
    print(f"   Заголовок: {reminder.title}")
    print(f"   Тип: {reminder.get_reminder_type_display()}")
    print(f"   Дата: {reminder.due_date}")
else:
    print("\n⚠️  Напоминание не создалось (это нормально для тестов без due_date)")
```

**Ожидаемый результат:**
```
✅ Клиент создан: Test User
   ID: 123
   Email: test@example.com
   Платежей: 1
   Напоминаний: 1

💳 Платеж:
   Сумма: 1000.00 zł
   Оплачено: 500.00 zł
   Статус: Частично оплачен
   Услуга: Учёба

🔔 Напоминание:
   Заголовок: Второй платёж: Учёба
   Тип: Оплата
   Дата: ...
```

---

### 2. Тест ClientService (3 минуты)

```python
from clients.services.orchestrators import ClientService
from decimal import Decimal

# Создание через сервис (упрощенный API)
client = ClientService.create_new_client(
    first_name="Maria",
    last_name="Test",
    email="maria.test@example.com",
    phone="+48999888777",
    citizenship="Belarus",
    application_purpose="work",
    initial_payment_amount=Decimal('1500'),
    send_welcome_email=False,
    passport_num="BB1234567"
)

print(f"✅ Клиент создан через сервис: {client}")

# Получить сводку
summary = ClientService.get_client_summary(client)

print(f"\n📊 Сводка:")
print(f"   Платежи:")
print(f"      Всего: {summary['payments']['total']}")
print(f"      Оплачено: {summary['payments']['total_paid']} zł")
print(f"      Осталось: {summary['payments']['total_due']} zł")
print(f"   Документы:")
print(f"      Всего: {summary['documents']['total']}")
print(f"      Недостает: {summary['documents']['missing']}")
print(f"   Статус:")
print(f"      Требует внимания: {summary['status']['needs_attention']}")
```

**Ожидаемый результат:**
```
✅ Клиент создан через сервис: Maria Test

📊 Сводка:
   Платежи:
      Всего: 1
      Оплачено: 0.00 zł
      Осталось: 1500.00 zł
   Документы:
      Всего: 0
      Недостает: 8  (примерно, зависит от checklists)
   Статус:
      Требует внимания: True
```

---

### 3. Запуск всех примеров (2 минуты)

```python
from examples.builder_usage_examples import run_all_examples

run_all_examples()
```

**Ожидаемый результат:**
Должны выполниться 6 примеров без ошибок с выводом информации о созданных клиентах.

---

### 4. Запуск тестов (5 минут)

```bash
# Запустить все тесты builder pattern
python manage.py test clients.tests.test_builders -v 2
```

**Ожидаемый результат:**
```
test_basic_client_creation ... ok
test_client_with_payment ... ok
test_client_with_auto_service_mapping ... ok
test_client_validation ... ok
test_basic_payment_creation ... ok
test_payment_with_partial_payment ... ok
test_payment_status_auto_calculation ... ok
test_payment_auto_reminder_creation ... ok
test_create_new_client ... ok
test_get_client_summary ... ok
...

Ran 14 tests in 2.341s

OK
```

---

### 5. Проверка обратной совместимости (2 минуты)

```python
# Старый способ должен продолжать работать!
from clients.models import Client, Payment
from decimal import Decimal

# Создание клиента старым способом
old_client = Client.objects.create(
    first_name="Old",
    last_name="Way",
    email="old.way@example.com",
    phone="+48111222333",
    citizenship="Ukraine",
    application_purpose="study"
)

print(f"✅ Старый способ работает: {old_client}")

# Создание платежа старым способом
old_payment = Payment.objects.create(
    client=old_client,
    service_description="study_service",
    total_amount=Decimal('500'),
    amount_paid=Decimal('0'),
    status='pending'
)

print(f"✅ Платеж создан старым способом: {old_payment}")
print(f"   Signals работают: напоминаний = {old_client.reminders.count()}")
```

---

## 🧹 Очистка тестовых данных

```python
# После тестирования можно удалить тестовых клиентов
from clients.models import Client

# Удалить всех тестовых клиентов
Client.objects.filter(email__contains="@example.com").delete()
Client.objects.filter(email__contains="test").delete()

print("✅ Тестовые данные очищены")
```

---

## 📋 Чек-лист проверки

- [ ] Создан клиент через `ClientBuilder`
- [ ] Создан клиент через `ClientService`
- [ ] Платеж создается автоматически
- [ ] Статус платежа определяется автоматически
- [ ] Service синхронизируется с purpose
- [ ] Reminder создается для partial payment
- [ ] Email отправка работает (опционально)
- [ ] Все тесты проходят
- [ ] Старый код продолжает работать
- [ ] Сводка клиента работает корректно

---

## ❓ Troubleshooting

### Ошибка: "Не указаны обязательные поля"
**Решение:** Убедитесь что вызвали `.with_basic_info()` и `.with_contact()`

### Ошибка: "Reminder не создался"
**Решение:** Reminder создается только для платежей со статусом `'partial'` и `due_date`. Проверьте эти поля.

### Ошибка: "Email не отправляется"
**Решение:** 
1. Проверьте настройки email в `settings.py`
2. Для тестов используйте `.with_notification(send_email=False)`

### Тесты падают
**Решение:**
```bash
# Убедитесь что база данных актуальна
python manage.py migrate

# Очистите кеш
python manage.py shell -c "from django.core.cache import cache; cache.clear()"
```

---

## 🚀 Следующие шаги

После успешного тестирования:

1. **Локальное тестирование OK** ✅
   ```bash
   git status
   # Проверьте что вы на ветке feature/builder-pattern
   ```

2. **Готово к интеграции в main:**
   ```bash
   # Переключиться на main
   git checkout main
   
   # Смержить feature ветку
   git merge feature/builder-pattern
   
   # Отправить на сервер
   git push origin main
   ```

3. **Или продолжить разработку:**
   ```bash
   # Остаться на feature ветке
   git checkout feature/builder-pattern
   
   # Добавить новые фичи...
   ```

---

**Помните:** Вы работаете в отдельной ветке `feature/builder-pattern`, основная ветка `main` не затронута! 🛡️
