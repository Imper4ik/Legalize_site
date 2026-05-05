#!/usr/bin/env bash
# start.sh - runtime server only
set -o errexit
set -o pipefail

mkdir -p "${MEDIA_ROOT:-/app/media}"

: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"