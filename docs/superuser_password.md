[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Permanent Superuser Password

To prevent the superuser password from changing between restarts, pass it via the `DJANGO_SUPERUSER_PASSWORD` environment variable. Example for local startup:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="your_secure_password"
./release.sh
```

## Storing Password in a File
If storing the password in an environment variable is inconvenient, place it in a file and specify the path in `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# password stored in /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./release.sh
```

The release script reads the configured password while creating the superuser. Existing passwords are changed only when `DJANGO_RESET_SUPERUSER_PASSWORD=true`. The priorities are:

1.  `DJANGO_SUPERUSER_PASSWORD` — used if specified.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — if the variable is missing but the file exists, the password is read from it.
3.  If neither the variable nor the file exists, superuser creation is skipped; no password is printed to logs.

---

# Polski <a name="polski"></a>

# Stałe Hasło Superużytkownika

Aby hasło superużytkownika nie zmieniało się pomiędzy restartami, przekaż je w zmiennej środowiskowej `DJANGO_SUPERUSER_PASSWORD`. Przykład dla lokalnego uruchomienia:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="twoje_bezpieczne_haslo"
./release.sh
```

## Przechowywanie Hasła w Pliku
Jeśli przechowywanie hasła w zmiennej środowiskowej jest niewygodne, umieść je w pliku i podaj ścieżkę w `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# hasło zapisane w /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./release.sh
```

Skrypt wydania odczytuje skonfigurowane hasło podczas tworzenia superużytkownika. Istniejące hasło jest zmieniane tylko przy `DJANGO_RESET_SUPERUSER_PASSWORD=true`. Priorytety są następujące:

1.  `DJANGO_SUPERUSER_PASSWORD` — jeśli podano, używana jest ta zmienna.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — jeśli brak zmiennej, ale plik istnieje, hasło jest czytane z niego.
3.  Jeśli nie ma ani zmiennej, ani pliku, tworzenie superużytkownika jest pomijane; hasło nie jest wypisywane w logach.

---

# Русский <a name="русский"></a>

# Постоянный пароль суперпользователя

Чтобы пароль суперпользователя не менялся между перезапусками, передайте его в переменной окружения `DJANGO_SUPERUSER_PASSWORD`. Пример для локального запуска:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="ваш_надежный_пароль"
./release.sh
```

## Хранение пароля в файле
Если хранить пароль в переменной окружения неудобно, положите его в файл и укажите путь в `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# пароль записан в /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./release.sh
```

Release-скрипт читает настроенный пароль при создании суперпользователя. Пароль существующего пользователя меняется только при `DJANGO_RESET_SUPERUSER_PASSWORD=true`. Приоритеты такие:

1.  `DJANGO_SUPERUSER_PASSWORD` — если указана, используется она.
2.  `DJANGO_SUPERUSER_PASSWORD_FILE` — если переменной нет, но есть файл, пароль читается из него.
3.  Если ни переменной, ни файла нет, создание суперпользователя пропускается; пароль в логи не выводится.
