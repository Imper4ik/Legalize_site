#!/usr/bin/env bash
# exit on error
set -o errexit

if ! command -v msgfmt >/dev/null 2>&1; then
  apt-get update
  apt-get install -y gettext
fi

if [ ! -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] && [ ! -f /usr/share/fonts/truetype/noto/NotoSans-Regular.ttf ]; then
  apt-get update
  apt-get install -y fonts-dejavu-core fonts-noto-core
fi

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --no-input
