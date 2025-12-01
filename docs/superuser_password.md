# Постоянный пароль суперпользователя

Чтобы пароль суперпользователя не менялся между перезапусками, передайте его в
переменной окружения `DJANGO_SUPERUSER_PASSWORD`. Пример для локального запуска:

```bash
export DJANGO_SUPERUSER_EMAIL="admin@example.com"
export DJANGO_SUPERUSER_PASSWORD="ваш_надежный_пароль"
./start.sh
```

## Хранение пароля в файле
Если хранить пароль в переменной окружения неудобно, положите его в файл и
укажите путь в `DJANGO_SUPERUSER_PASSWORD_FILE`:

```bash
# пароль записан в /etc/secrets/django_superuser_password
export DJANGO_SUPERUSER_PASSWORD_FILE="/etc/secrets/django_superuser_password"
./start.sh
```

Скрипт старта подставит содержимое файла как пароль и не будет генерировать
новый при каждом деплое. Приоритеты такие:

1. `DJANGO_SUPERUSER_PASSWORD` — если указана, используется она.
2. `DJANGO_SUPERUSER_PASSWORD_FILE` — если переменной нет, но есть файл,
   пароль читается из него.
3. Если ни переменной, ни файла нет, скрипт создаст одноразовый пароль и
   выведет его в лог запуска.
