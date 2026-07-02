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

## Deliberate Trade-off: Searchable Plaintext Fields

Not every PII field is encrypted, by design. `Client.first_name`,
`last_name`, `email` and `phone` are stored in plaintext so the staff
client-list search (`icontains` lookups) and unique-email checks keep
working — Fernet ciphertexts cannot be substring-searched or indexed.
High-sensitivity values (passport number, questionnaire payloads, email
bodies/recipients, onboarding answers — 25 fields in total) are encrypted,
and identifiers used for lookups (onboarding tokens, authority case
numbers) additionally carry HMAC hashes for exact-match search. If the
plaintext name/contact fields ever need encryption too, staff search must
first be reworked (e.g. dedicated search hashes or an external index);
until then this trade-off is accepted and documented here.

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

## Świadomy kompromis: pola przeszukiwalne w postaci jawnej

Nie każde pole PII jest szyfrowane — celowo. `Client.first_name`,
`last_name`, `email` i `phone` są przechowywane jawnie, aby wyszukiwarka
listy klientów (`icontains`) i kontrola unikalności e-maila działały —
szyfrogramów Fernet nie da się przeszukiwać po fragmencie ani indeksować.
Dane wysokiego ryzyka (numer paszportu, ankiety, treści e-maili — łącznie
25 pól) są szyfrowane, a identyfikatory używane do wyszukiwania (tokeny
onboardingu, numery spraw urzędu) mają dodatkowo hasze HMAC do dopasowań
dokładnych. Zaszyfrowanie pól imienia/kontaktu wymagałoby najpierw
przebudowy wyszukiwarki — do tego czasu kompromis jest zaakceptowany.

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

## Осознанный компромисс: поля, доступные для поиска в открытом виде

Не все поля PII шифруются — это сделано намеренно. `Client.first_name`,
`last_name`, `email` и `phone` хранятся в открытом виде, чтобы работал
поиск по списку клиентов (`icontains`) и проверка уникальности e-mail —
шифртексты Fernet нельзя искать по подстроке или индексировать.
Высокочувствительные данные (номер паспорта, анкеты, тексты писем — всего
25 полей) зашифрованы, а идентификаторы для поиска (токены онбординга,
номера дел ужонда) дополнительно имеют HMAC-хэши для точного совпадения.
Если понадобится шифровать и поля имени/контактов, сначала придётся
переделать поиск — до этого компромисс принят и зафиксирован здесь.
