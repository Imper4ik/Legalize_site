#!/usr/bin/env bash
# exit on error
set -o errexit

pip install --upgrade pip

# Принудительно удаляем ВСЕ старые почтовые пакеты
pip uninstall -y django-sendgrid-v5 sendgrid django-anymail

# Устанавливаем все заново
pip install -r requirements.txt

# Ваши стандартные команды
python manage.py collectstatic --no-input
python manage.py migrate