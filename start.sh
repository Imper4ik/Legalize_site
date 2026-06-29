#!/usr/bin/env bash
# start.sh - runtime server
set -o errexit
set -o pipefail

mkdir -p "${MEDIA_ROOT:-/app/media}"

# Railway/Nixpacks deployments may start the web process even when a configured
# release phase was skipped. Apply pending migrations before Gunicorn so ORM
# code can never query a column that has not reached PostgreSQL yet.
# Set RUN_MIGRATIONS_ON_START=false only for a deployment that runs migrations
# through a separate, guaranteed pre-deploy job.
: "${RUN_MIGRATIONS_ON_START:=true}"
case "${RUN_MIGRATIONS_ON_START}" in
  1|true|TRUE|yes|YES|on|ON)
    echo "Running migrations before starting the web server..."
    python manage.py migrate --no-input
    ;;
esac

: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=3}"
: "${WEB_THREADS:=2}"
: "${GUNICORN_TIMEOUT:=120}"
: "${GUNICORN_MAX_REQUESTS:=1200}"
: "${GUNICORN_MAX_REQUESTS_JITTER:=200}"
: "${ENABLE_BACKGROUND_AUTOMATION_LOOP:=false}"

case "${ENABLE_BACKGROUND_AUTOMATION_LOOP}" in
  1|true|TRUE|yes|YES|on|ON)
    python manage.py run_background_automation_loop --loop &
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
  --logger-class legalize_site.gunicorn_logging.RedactingLogger \
  --preload
