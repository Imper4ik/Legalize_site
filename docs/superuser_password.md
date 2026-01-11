[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Permanent Superuser Password

To prevent the superuser password from changing between restarts, pass it via the `DJANGO_SUPERUSER_PASSWORD` environment variable. Example for local startup:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="your_secure_password"
./start.sh
```

## Storing Password in a File
If storing the password in an environment variable is inconvenient, place it in a file and specify the path in `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# password stored in /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./start.sh
```

The start script will substitute the file contents as the password and will not generate a new one on each deploy. The priorities are:

1.  `DJANGO_SUPERUSER_PASSWORD` — used if specified.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — if the variable is missing but the file exists, the password is read from it.
3.  If neither the variable nor the file exists, the script will create a one-time password and print it to the startup log.

---

# Polski <a name="polski"></a>

# Stałe Hasło Superużytkownika

Aby hasło superużytkownika nie zmieniało się pomiędzy restartami, przekaż je w zmiennej środowiskowej `DJANGO_SUPERUSER_PASSWORD`. Przykład dla lokalnego uruchomienia:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="twoje_bezpieczne_haslo"
./start.sh
```

## Przechowywanie Hasła w Pliku
Jeśli przechowywanie hasła w zmiennej środowiskowej jest niewygodne, umieść je w pliku i podaj ścieżkę w `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# hasło zapisane w /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./start.sh
```

Skrypt startowy wstawi zawartość pliku jako hasło i nie będzie generował nowego przy każdym wdrożeniu. Priorytety są następujące:

1.  `DJANGO_SUPERUSER_PASSWORD` — jeśli podano, używana jest ta zmienna.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — jeśli brak zmiennej, ale plik istnieje, hasło jest czytane z niego.
3.  Jeśli nie ma ani zmiennej, ani pliku, skrypt stworzy jednorazowe hasło i wypisze je w logach startowych.

---

# Русский <a name="русский"></a>

# Постоянный пароль суперпользователя

Чтобы пароль суперпользователя не менялся между перезапусками, передайте его в переменной окружения `DJANGO_SUPERUSER_PASSWORD`. Пример для локального запуска:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="ваш_надежный_пароль"
./start.sh
```

## Хранение пароля в файле
Если хранить пароль в переменной окружения неудобно, положите его в файл и укажите путь в `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# пароль записан в /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./start.sh
```

Скрипт старта подставит содержимое файла как пароль и не будет генерировать новый при каждом деплое. Приоритеты такие:

1.  `DJANGO_SUPERUSER_PASSWORD` — если указана, используется она.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — если переменной нет, но есть файл, пароль читается из него.
3.  Если ни переменной, ни файла нет, скрипт создаст одноразовый пароль и выведет его в лог запуска.
