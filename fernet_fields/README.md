[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Fernet Fields (Encryption)

This folder contains utilities for encrypting data in the database.

## Purpose
Ensures security of sensitive data (passport numbers, case numbers) (PII - Personally Identifiable Information). Even if the database is compromised (SQL Dump), an attacker will only see encrypted strings, not real data.

## How it works (`fields.py`)
*   **`EncryptedTextField`**: Custom Django model field.
    *   **On save (`get_prep_value`)**: Encrypts text using a key from settings (`settings.FERNET_KEYS`).
    *   **On read (`from_db_value`, `to_python`)**: Decrypts data back to text.
*   **Key Rotation**: Uses `MultiFernet`, allowing a list of keys. This is useful for security key rotation (a new key can be added, and old data will still be readable until re-saved with the new key).

## Usage
Used in models (e.g., `clients.models.Client`) like this:
```python
passport_num = EncryptedTextField(...)
```
For the developer, the field behaves like normal text; all encryption magic happens "under the hood".

---

# Polski <a name="polski"></a>

# Fernet Fields (Szyfrowanie)

Folder zawiera narzędzia do szyfrowania danych w bazie danych.

## Cel
Zapewnia bezpieczeństwo wrażliwych danych (numery paszportów, numery spraw) (PII - Dane Osobowe). Nawet jeśli baza danych wycieknie (SQL Dump), atakujący zobaczy tylko zaszyfrowane ciągi znaków, a nie prawdziwe dane.

## Jak to działa (`fields.py`)
*   **`EncryptedTextField`**: Niestandardowe pole modelu Django.
    *   **Przy zapisie (`get_prep_value`)**: Szyfruje tekst używając klucza z ustawień (`settings.FERNET_KEYS`).
    *   **Przy odczycie (`from_db_value`, `to_python`)**: Odszyfrowuje dane z powrotem do tekstu.
*   **Rotacja Kluczy**: Używa `MultiFernet`, co pozwala na posiadanie listy kluczy. Jest to przydatne przy rotacji kluczy bezpieczeństwa (można dodać nowy klucz, a stare dane wciąż będą czytelne póki nie zostaną zapisane ponownie nowym kluczem).

## Użycie
W modelach (np. `clients.models.Client`) używa się tak:
```python
passport_num = EncryptedTextField(...)
```
Dla programisty pole zachowuje się jak zwykły tekst, cała magia szyfrowania dzieje się "pod maską".

---

# Русский <a name="русский"></a>

# Fernet Fields (Шифрование)

Эта папка содержит утилиты для шифрования данных в базе данных.

## Назначение
Обеспечивает безопасность чувствительных данных (номера паспортов, номера дел) (PII - Personally Identifiable Information). Даже если база данных будет скомпрометирована (SQL Dump), злоумышленник увидит только зашифрованные строки, а не реальные данные.

## Как это работает (`fields.py`)
*   **`EncryptedTextField`**: Кастомное поле модели Django.
    *   **При сохранении (`get_prep_value`)**: Шифрует текст, используя ключ из настроек (`settings.FERNET_KEYS`).
    *   **При чтении (`from_db_value`, `to_python`)**: Расшифровывает данные обратно в текст.
*   **Ротация ключей**: Использует `MultiFernet`, что позволяет иметь список ключей. Это полезно для ротации ключей безопасности (можно добавить новый ключ, и старые данные все еще будут читаться, пока не будут пересохранены новым ключом).

## Использование
В моделях (например, `clients.models.Client`) используется так:
```python
passport_num = EncryptedTextField(...)
```
Для разработчика поле ведет себя как обычный текст, вся магия шифрования происходит "под капотом".
