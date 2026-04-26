#!/usr/bin/env bash
# exit on error
set -o errexit

fonts_missing=false
if [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] && [ ! -f /usr/share/fonts/truetype/noto/NotoSans-Regular.ttf ]; then
  fonts_missing=true
fi

if ! command -v msgfmt >/dev/null 2>&1 || ! command -v tesseract >/dev/null 2>&1 || ! command -v pdftoppm >/dev/null 2>&1 || ! command -v pg_dump >/dev/null 2>&1 || [ "$fonts_missing" = true ]; then
  apt-get update
  apt-get install -y gettext fonts-dejavu-core fonts-noto-core tesseract-ocr tesseract-ocr-eng tesseract-ocr-pol poppler-utils postgresql-client
fi

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors
python manage.py compilemessages --ignore "venv" --ignore ".venv"

# pytest is intentionally omitted from production build; tests run in GitHub Actions only.
python manage.py collectstatic --no-input
