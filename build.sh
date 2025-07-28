#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate

# --- ДОБАВЬТЕ ЭТУ СТРОКУ В КОНЕЦ ---
python promote_user.py