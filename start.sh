#!/usr/bin/env bash
# start.sh - runtime server only
set -o errexit
set -o pipefail

mkdir -p "${MEDIA_ROOT:-/app/media}"

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=3}"
: "${WEB_THREADS:=2}"
: "${GUNICORN_TIMEOUT:=120}"
: "${GUNICORN_MAX_REQUESTS:=1200}"
: "${GUNICORN_MAX_REQUESTS_JITTER:=200}"
: "${ENABLE_WEEKLY_DOCUMENT_REMINDER_LOOP:=true}"

case "${ENABLE_WEEKLY_DOCUMENT_REMINDER_LOOP}" in
  1|true|TRUE|yes|YES|on|ON)
    python manage.py run_weekly_document_reminders --loop &
    ;;
esac

exec gunicorn legalize_site.wsgi:application \
  --bind 0.0.0.0:"${PORT}" \
  --workers "${WEB_CONCURRENCY}" \
  --threads "${WEB_THREADS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --max-requests "${GUNICORN_MAX_REQUESTS}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER}" \
  --access-logfile - \
  --preload
