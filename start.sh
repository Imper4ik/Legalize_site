#!/usr/bin/env bash
set -o errexit

# EXPERIMENTAL: Attempt to install Tesseract at runtime
# This usually fails due to lack of root permissions in the container
echo "Attempting to install Tesseract via start.sh..."
if apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-eng tesseract-ocr-pol poppler-utils; then
  echo "SUCCESS: Tesseract installed."
else
  echo "WARNING: Failed to install Tesseract (Permission Denied). Proceeding without it."
fi

# Ensure DejaVu fonts are available at runtime (not only during build).
# Nixpacks should include them in the final image, but we double-check and
# install them when possible to avoid missing glyphs in PDF rendering.
if ! ls /nix/store/*dejavu_fonts* >/dev/null 2>&1; then
  if command -v nix-env >/dev/null 2>&1; then
    echo "dejavu_fonts not found in /nix/store; installing via nix-env..."
    nix-env -iA nixpkgs.dejavu_fonts
  else
    echo "Warning: dejavu_fonts not found and nix-env is unavailable; fonts may be missing at runtime."
  fi
else
  echo "dejavu_fonts present in /nix/store."
fi

# === Настройка суперюзера по умолчанию (email: nindse@gmail.com) ===
# Пароль можно передать через переменную окружения DJANGO_SUPERUSER_PASSWORD.
# Если она не указана, скрипт сгенерирует одноразовый пароль и выведет его
# в лог запуска, чтобы аккаунт точно создался на стенде.
DEFAULT_SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-"nindse@gmail.com"}
DEFAULT_SUPERUSER_USERNAME=${DJANGO_SUPERUSER_USERNAME:-"admin"}
SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-}

# Позволяет хранить постоянный пароль в файле (например, в томе или Docker secret)
# и передавать путь к нему через DJANGO_SUPERUSER_PASSWORD_FILE. Это исключает
# генерацию нового пароля при каждом деплое, если переменная окружения не задана.
if [ -z "$SUPERUSER_PASSWORD" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD_FILE" ] && [ -f "$DJANGO_SUPERUSER_PASSWORD_FILE" ]; then
  SUPERUSER_PASSWORD=$(cat "$DJANGO_SUPERUSER_PASSWORD_FILE")
fi

if [ -z "$SUPERUSER_PASSWORD" ]; then
  SUPERUSER_PASSWORD=$(python - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
print("".join(secrets.choice(alphabet) for _ in range(16)))
PY
  )
  echo "DJANGO_SUPERUSER_PASSWORD was not set; generated password: $SUPERUSER_PASSWORD"
fi

export DJANGO_SUPERUSER_EMAIL="$DEFAULT_SUPERUSER_EMAIL"
export DJANGO_SUPERUSER_USERNAME="$DEFAULT_SUPERUSER_USERNAME"
export DJANGO_SUPERUSER_PASSWORD="$SUPERUSER_PASSWORD"
# === конец настройки суперюзера ===

python manage.py migrate --no-input

# Ensure translation catalogs are compiled so UI strings and checklist items
# render in the selected language. This is a no-op if msgfmt is unavailable
# (e.g., in minimal containers) but prevents untranslated Polish labels when
# it is present.
if command -v msgfmt >/dev/null 2>&1; then
  python manage.py compilemessages --ignore "venv" --ignore ".venv" || \
    echo "Warning: compilemessages failed; using existing translations"
else
  echo "msgfmt not found; skipping compilemessages"
fi

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
