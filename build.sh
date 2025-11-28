#!/usr/bin/env bash
# exit on error
set -o errexit

# Ensure gettext is available, but do not fail the entire build if installation
# is blocked (e.g., by a restricted network or package mirror). Translations
# remain usable from existing ``*.mo`` files even when compilation is skipped.
if command -v msgfmt >/dev/null 2>&1; then
  MSGFMT_AVAILABLE=1
elif command -v apt-get >/dev/null 2>&1; then
  echo "Installing gettext so translation catalogs can be compiled..."
  if apt-get update && apt-get install -y gettext; then
    MSGFMT_AVAILABLE=1
  else
    echo "Warning: gettext installation failed; skipping compilemessages"
    MSGFMT_AVAILABLE=0
  fi
else
  echo "msgfmt not found and apt-get is unavailable; skipping compilemessages"
  MSGFMT_AVAILABLE=0
fi

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors.
if [ "${MSGFMT_AVAILABLE:-0}" -eq 1 ]; then
  python manage.py compilemessages --ignore "venv" --ignore ".venv"
else
  echo "msgfmt unavailable; skipping compilemessages"
fi

python manage.py collectstatic --no-input
