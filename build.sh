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

if ! command -v pg_dump > /dev/null 2>&1; then
  echo "Installing PostgreSQL 17 client from official repository..."
  apt-get update
  apt-get install -y curl ca-certificates gnupg
  install -d /usr/share/postgresql-common/pgdg
  curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list
  apt-get update
  apt-get install -y postgresql-client-17
  echo "PostgreSQL 17 client installed successfully"
elif pg_dump --version | grep -q "15\."; then
  echo "Upgrading PostgreSQL client from version 15 to 17..."
  apt-get update
  apt-get install -y curl ca-certificates gnupg
  install -d /usr/share/postgresql-common/pgdg
  curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail https://www.postgresql.org/media/keys/ACCC4CF8.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list
  apt-get update
  apt-get install -y postgresql-client-17
  echo "PostgreSQL client upgraded to version 17"
fi

pip install --upgrade pip
pip install -r requirements.txt

# Skip translating files shipped in the virtualenv to avoid permission errors
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --no-input
