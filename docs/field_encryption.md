[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Field-level Encryption and Key Rotation

This project uses `django-fernet-fields` (via `fernet_fields` app) to encrypt PII (Personally Identifiable Information) at rest for the `Client` model (passport and case numbers).

## Configuration

Set the Fernet keys via the `FERNET_KEYS` environment variable. Provide a comma-separated list where the first key is used for new encryption, and the remaining keys are used for decryption (allowing key rotation).

### Generate a key:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

### Example:

```bash
export FERNET_KEYS="newest_key,previous_key"
```

If `FERNET_KEYS` is not provided, a deterministic key derived from `SECRET_KEY` is used for **local development only**.

## Key Rotation Procedure

1.  **Generate a new key** (see command above).
2.  **Update `FERNET_KEYS`** so the new key is first, followed by previous keys.
3.  **Deploy** the configuration change.
4.  **Re-encrypt existing rows**: Run a management script that loads and saves all `Client` objects. This re-writes them using the first key in the list.
5.  **Remove the old key** from `FERNET_KEYS` after re-encryption is verified and all services are updated.

## Logging Policy

*   **Avoid logging PII fields** (`passport_num`, `case_number`) directly.
*   The system includes a log filter that redacts known PII field names in log messages to prevent accidental leakage.

---

# Polski <a name="polski"></a>

# Szyfrowanie Poziomu Pola i Rotacja Kluczy

Ten projekt używa biblioteki (poprzez folder `fernet_fields`) do szyfrowania PII (Danych Osobowych) w spoczynku dla modelu `Client` (numery paszportów i numery spraw).

## Konfiguracja

Ustaw klucze Fernet za pomocą zmiennej środowiskowej `FERNET_KEYS`. Podaj listę oddzieloną przecinkami, gdzie pierwszy klucz jest używany do nowego szyfrowania, a pozostałe klucze służą do odszyfrowywania (co umożliwia rotację kluczy).

### Generowanie klucza:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

### Przykład:

```bash
export FERNET_KEYS="najnowszy_klucz,poprzedni_klucz"
```

Jeśli `FERNET_KEYS` nie zostanie podany, używany jest deterministyczny klucz pochodny od `SECRET_KEY` - **tylko do rozwoju lokalnego**.

## Procedura Rotacji Kluczy

1.  **Wygeneruj nowy klucz** (patrz polecenie powyżej).
2.  **Zaktualizuj `FERNET_KEYS`**, tak aby nowy klucz był pierwszy, a po nim poprzednie klucze.
3.  **Wdróż** zmianę konfiguracji.
4.  **Przeszyfruj istniejące wiersze**: Uruchom skrypt, który pobiera i zapisuje wszystkie obiekty `Client`. To spowoduje ich ponowny zapis przy użyciu pierwszego klucza z listy.
5.  **Usuń stary klucz** z `FERNET_KEYS` po zweryfikowaniu przeszyfrowania i aktualizacji wszystkich usług.

## Polityka Logowania

*   **Unikaj logowania pól PII** (`passport_num`, `case_number`) bezpośrednio.
*   System zawiera filtr logów, który redaguje (ukrywa) znane nazwy pól PII w wiadomościach logowania, aby zapobiec przypadkowemu wyciekowi.

---

# Русский <a name="русский"></a>

# Шифрование на уровне полей и ротация ключей

В этом проекте используется шифрование (через приложение `fernet_fields`) для защиты PII (Персональных данных) в состоянии покоя для модели `Client` (номера паспортов и номера дел).

## Конфигурация

Установите ключи Fernet через переменную окружения `FERNET_KEYS`. Укажите список через запятую, где первый ключ используется для нового шифрования, а остальные ключи используются для расшифровки (что позволяет проводить ротацию ключей).

### Генерация ключа:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

### Пример:

```bash
export FERNET_KEYS="новейший_ключ,предыдущий_ключ"
```

Если `FERNET_KEYS` не указан, для **локальной разработки** используется детерминированный ключ, производный от `SECRET_KEY`.

## Процедура ротации ключей

1.  **Сгенерируйте новый ключ** (см. команду выше).
2.  **Обновите `FERNET_KEYS`**, чтобы новый ключ стоял первым, за ним следовали предыдущие.
3.  **Задеплойте** изменение конфигурации.
4.  **Перешифруйте существующие строки**: Запустите скрипт управления, который загружает и сохраняет все объекты `Client`. Это перезапишет их, используя первый ключ в списке.
5.  **Удалите старый ключ** из `FERNET_KEYS` после проверки перешифровки и обновления всех сервисов.

## Политика логирования

*   **Избегайте прямого логирования полей PII** (`passport_num`, `case_number`).
*   Система включает фильтр логов, который скрывает известные имена полей PII в сообщениях логов, чтобы предотвратить случайную утечку.
