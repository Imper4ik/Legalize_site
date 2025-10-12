#!/usr/bin/env bash
set -o errexit

# 1. Собрать статические файлы
python manage.py collectstatic --no-input  # <--- КРИТИЧЕСКОЕ ДОБАВЛЕНИЕ

# 2. Выполнить миграции
python manage.py migrate --no-input

# 3. Запустить Gunicorn
: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"