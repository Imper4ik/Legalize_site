#!/usr/bin/env bash
# exit on error
set -o errexit

# System dependencies like gettext and fonts are now managed via nixpacks.toml

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --no-input
