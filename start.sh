#!/usr/bin/env bash
set -o errexit

# System dependencies (Tesseract, PostgreSQL client) are now managed via nixpacks.toml at build-time.
# This ensures faster startup and avoids permission issues during runtime.
echo "System dependencies verified via nixpacks."

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

if not User.objects.filter(email=email).exists() and not User.objects.filter(username=username).exists():
    print(f"Creating superuser {username!r} ({email!r})")
    try:
        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
    except Exception as e:
        print(f"Could not create superuser (possibly created by another worker): {e}")
else:
    print(f"Superuser {username!r} or email {email!r} already exists, skipping")
EOF
fi
# === конец блока создания суперюзера ===

: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"
