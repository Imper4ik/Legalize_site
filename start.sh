#!/usr/bin/env bash
set -o errexit

python manage.py migrate --no-input

# Ensure translation catalogs are compiled so UI strings and checklist items
# render in the selected language. Uses gettext tooling when available and
# falls back to a pure-Python compilation to avoid binary artifacts in the
# repository.
python manage.py shell <<'PY'
from legalize_site.utils.i18n import compile_message_catalogs

compile_message_catalogs()
PY

# === Одноразовое создание суперюзера через env-переменные ===
if [ "$DJANGO_SUPERUSER_EMAIL" ] && [ "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "Checking/creating superuser..."
  python manage.py shell << 'EOF'
from django.contrib.auth import get_user_model
import os

User = get_user_model()

email = os.environ["DJANGO_SUPERUSER_EMAIL"]
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]
username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")

if not User.objects.filter(email=email).exists():
    print(f"Creating superuser {email!r}")
    # Для стандартного User: username + email + password
    User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
    )
else:
    print(f"Superuser {email!r} already exists, skipping")
EOF
fi
# === конец блока создания суперюзера ===

: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"
