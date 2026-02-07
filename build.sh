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

if ! command -v pg_dump >/dev/null 2>&1; then
  apt-get update
  apt-get install -y curl ca-certificates gnupg

  # Railway Postgres is currently version 17, while Debian Bookworm default
  # postgresql-client is 15. Prefer 17 to avoid pg_dump server version mismatch.
  . /etc/os-release
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg
  echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list

  apt-get update
  apt-get install -y postgresql-client-17 || apt-get install -y postgresql-client
fi

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --no-input
