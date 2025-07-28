#!/usr/bin/env bash
# exit on error
set -o errexit

# Обновляем сам установщик, чтобы избежать проблем
pip install --upgrade pip

# Принудительно удаляем старые версии перед установкой
pip uninstall -y django-sendgrid-v5 sendgrid

# Устанавливаем все пакеты заново из вашего requirements.txt
pip install -r requirements.txt

# Ваши стандартные команды
python manage.py collectstatic --no-input
python manage.py migrate