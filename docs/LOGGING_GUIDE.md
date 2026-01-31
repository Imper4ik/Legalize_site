# 📝 Руководство по логированию

## Где добавить логи

### 1. В views (clients/views.py)

```python
import logging

logger = logging.getLogger(__name__)

def client_create_view(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            
            # ✅ Логируем создание клиента
            logger.info(
                f"Client created: {client.email}",
                extra={
                    'client_id': client.id,
                    'email': client.email,
                    'purpose': client.application_purpose,
                    'user': request.user.username if request.user.is_authenticated else 'anonymous'
                }
            )
            
            return redirect('clients:client_detail', pk=client.id)
        else:
            # ✅ Логируем ошибки валидации
            logger.warning(
                "Client creation failed - validation error",
                extra={'errors': form.errors.as_json()}
            )
```

### 2. В OCR парсере (clients/services/parsers/)

```python
import logging

logger = logging.getLogger(__name__)

def parse_wezwanie(file_path):
    try:
        logger.info(f"Starting OCR for document", extra={'file': file_path})
        
        text = extract_text_with_ocr(file_path)
        
        # Поиск case_number
        case_match = re.search(CASE_NUMBER_PATTERN, text)
        if case_match:
            case_number = case_match.group(1)
            logger.info(
                "Case number found",
                extra={'case_number': case_number[:4] + '***'}  # Частично скрыт
            )
        else:
            logger.warning("Case number not found in document")
        
        return result
        
    except Exception as e:
        logger.error(
            "OCR parsing failed",
            extra={'file': file_path, 'error': str(e)},
            exc_info=True  # Добавляет полный traceback
        )
        raise
```

### 3. В signals (clients/signals.py)

```python
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Payment)
def sync_payment_reminder_on_save(sender, instance, **kwargs):
    if instance.status == 'partial' and instance.due_date:
        logger.info(
            "Creating payment reminder",
            extra={
                'payment_id': instance.id,
                'client_id': instance.client.id,
                'due_date': instance.due_date.isoformat(),
                'amount_due': str(instance.amount_due)
            }
        )
        
        Reminder.objects.update_or_create(...)
    else:
        Reminder.objects.filter(payment=instance).delete()
        logger.debug(f"Payment reminder deleted for payment {instance.id}")
```

### 4. В Builder (clients/services/builders/)

```python
import logging

logger = logging.getLogger(__name__)

class ClientBuilder:
    def build(self):
        try:
            client = Client.objects.create(**self._client_data)
            
            logger.info(
                "Client built successfully",
                extra={
                    'client_id': client.id,
                    'builder': self.__class__.__name__,
                    'has_payment': bool(self._payment_data)
                }
            )
            
            # Создание платежа
            if self._payment_data:
                payment = Payment.objects.create(...)
                logger.info(
                    "Payment created via builder",
                    extra={'payment_id': payment.id, 'amount': payment.total_amount}
                )
            
            return client
            
        except Exception as e:
            logger.error(
                "Client build failed",
                extra={'error': str(e), 'data': self._client_data},
                exc_info=True
            )
            raise
```

### 5. В middleware (core/middleware/rate_limit.py)

```python
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    def __call__(self, request):
        ip_address = self._get_client_ip(request)
        
        if not self._check_rate_limit(request, ip_address):
            logger.warning(
                "Rate limit exceeded",
                extra={
                    'ip': ip_address,
                    'path': request.path,
                    'method': request.method,
                    'user': request.user.username if request.user.is_authenticated else 'anonymous'
                }
            )
            return self._rate_limit_response()
        
        return self.get_response(request)
```

### 6. При отправке email

```python
import logging

logger = logging.getLogger(__name__)

def send_required_documents_email(client):
    try:
        logger.info(
            "Sending required documents email",
            extra={'client_id': client.id, 'email': client.email}
        )
        
        send_mail(...)
        
        logger.info(
            "Email sent successfully",
            extra={'client_id': client.id}
        )
        
    except Exception as e:
        logger.error(
            "Failed to send email",
            extra={'client_id': client.id, 'error': str(e)},
            exc_info=True
        )
        # Не бросаем исключение - email non-critical
```

---

## Уровни логирования

```python
# DEBUG - детальная отладочная информация
logger.debug("Query executed in 0.05s", extra={'query': sql})

# INFO - обычные операции
logger.info("Client created", extra={'client_id': 123})

# WARNING - предупреждения (не критично)
logger.warning("Payment overdue", extra={'payment_id': 456})

# ERROR - ошибки (требуют внимания)
logger.error("OCR failed", extra={'doc_id': 789}, exc_info=True)

# CRITICAL - критические ошибки (система падает)
logger.critical("Database connection lost!", exc_info=True)
```

---

## Файлы логов

### Локально (в папке `logs/`):
- `app.log` - все события приложения
- `errors.log` - только ошибки (ERROR+)
- `security.log` - security события

### На Railway:
- Все логи автоматически в stdout/stderr
- Видны в Railway Dashboard → Logs
- Можно экспортировать или интегрировать с внешними сервисами

---

## Примеры команд для просмотра

### Локально:
```bash
# Последние 50 строк app логов
tail -50 logs/app.log

# Следить за логами в реальном времени
tail -f logs/app.log

# Только ошибки
tail -f logs/errors.log

# Поиск по логам
grep "Client created" logs/app.log

# Поиск ошибок OCR
grep "OCR" logs/errors.log
```

### Railway:
```bash
# Через CLI
railway logs

# Следить в реальном времени
railway logs --follow

# Только ошибки (stderr)
railway logs --stderr
```

---

## Best Practices

### ✅ DO:
- Логируйте важные бизнес-события (создание клиента, платежа, документа)
- Логируйте все ошибки с `exc_info=True`
- Используйте `extra={}` для структурированных данных
- Скрывайте чувствительные данные (пароли, полные номера паспортов)

### ❌ DON'T:
- Не логируйте пароли, токены, API ключи
- Не логируйте каждый запрос в production (только ошибки)
- Не используйте `print()` вместо `logger`
- Не логируйте огромные объекты целиком

---

## Интеграция с Sentry (опционально)

```bash
pip install sentry-sdk
```

```python
# settings/base.py
import sentry_sdk

if not DEBUG:
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        environment="production",
        traces_sample_rate=0.1,  # 10% запросов
    )
```

Тогда все ERROR+ логи автоматически отправятся в Sentry!
