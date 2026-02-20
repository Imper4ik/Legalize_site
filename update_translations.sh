#!/usr/bin/env bash
set -e

echo "========================================="
echo "Updating Django translations for ru, pl, en"
echo "========================================="

echo ""
echo "[1/2] Running makemessages..."
python manage.py makemessages -l pl -l ru -l en -i venv -i env -i .venv -i frontend -i "frontend/node_modules/*" -a

echo ""
echo "[2/2] Running compilemessages..."
python manage.py compilemessages -i venv -i env -i .venv -i frontend

echo ""
echo "========================================="
echo "SUCCESS! Translations updated and compiled."
echo "========================================="
