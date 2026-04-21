#!/usr/bin/env bash
set -o errexit
set -o pipefail

BOOTSTRAP_SUPERUSER_MODE=${DJANGO_BOOTSTRAP_SUPERUSER:-auto}
RESET_SUPERUSER_PASSWORD=${DJANGO_RESET_SUPERUSER_PASSWORD:-0}
SUPERUSER_EMAIL=${DJANGO_SUPERUSER_EMAIL:-}
SUPERUSER_PASSWORD=${DJANGO_SUPERUSER_PASSWORD:-}

if [ -z "$SUPERUSER_PASSWORD" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD_FILE:-}" ] && [ -f "$DJANGO_SUPERUSER_PASSWORD_FILE" ]; then
  SUPERUSER_PASSWORD=$(cat "$DJANGO_SUPERUSER_PASSWORD_FILE")
fi

should_bootstrap_superuser=false
case "${BOOTSTRAP_SUPERUSER_MODE}" in
  1|true|TRUE|yes|YES|on|ON)
    should_bootstrap_superuser=true
    ;;
  auto|AUTO)
    if [ -n "$SUPERUSER_EMAIL" ]; then
      should_bootstrap_superuser=true
    fi
    ;;
esac

python manage.py bootstrap_user_model_migration
python manage.py migrate --no-input

if [ "$should_bootstrap_superuser" = true ]; then
  if [ -z "$SUPERUSER_EMAIL" ]; then
    echo "Skipping superuser bootstrap: DJANGO_SUPERUSER_EMAIL is not configured."
  else
    export DJANGO_SUPERUSER_EMAIL="$SUPERUSER_EMAIL"
    if [ -n "$SUPERUSER_PASSWORD" ]; then
      export DJANGO_SUPERUSER_PASSWORD="$SUPERUSER_PASSWORD"
    fi
    export DJANGO_RESET_SUPERUSER_PASSWORD="$RESET_SUPERUSER_PASSWORD"

    echo "Checking/creating superuser..."
    python manage.py shell << 'EOF'
from django.contrib.auth import get_user_model
import os

User = get_user_model()

email = os.environ["DJANGO_SUPERUSER_EMAIL"]
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()
reset_password = os.environ.get("DJANGO_RESET_SUPERUSER_PASSWORD", "").lower() in {"1", "true", "yes", "on"}

user = User.objects.filter(email=email).first()

if user is None:
    if not password:
        print(
            f"Skipping superuser creation for {email!r}: "
            "DJANGO_SUPERUSER_PASSWORD is not configured."
        )
    else:
        user = User.objects.create_superuser(email=email, password=password)
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        print(f"Created superuser for {email!r}")
else:
    changed_fields = []
    if not user.is_staff:
        user.is_staff = True
        changed_fields.append("is_staff")
    if not user.is_superuser:
        user.is_superuser = True
        changed_fields.append("is_superuser")
    if not user.is_active:
        user.is_active = True
        changed_fields.append("is_active")
    if password and reset_password:
        user.set_password(password)
        changed_fields.append("password")
    if changed_fields:
        user.save()
        print(f"Updated superuser for {email!r}: {', '.join(changed_fields)}")
    else:
        print(f"Superuser for {email!r} is already up to date")
EOF
  fi
else
  echo "Superuser bootstrap skipped."
fi

: "${PORT:=8000}"
exec gunicorn legalize_site.wsgi:application --bind 0.0.0.0:"${PORT}"
