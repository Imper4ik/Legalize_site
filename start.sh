#!/usr/bin/env bash
set -o errexit

python manage.py migrate --no-input

: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"
