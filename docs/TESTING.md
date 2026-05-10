# Testing

## Local commands

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py test --noinput
pytest --maxfail=1 -q --cov-fail-under=70
ruff check .
mypy clients/services clients/use_cases database_media fernet_fields legalize_site/security.py legalize_site/cron_views.py legalize_site/backups.py --config-file mypy.ini
bandit -r clients legalize_site submissions users database_media fernet_fields translations -x "*/migrations/*,*/tests/*"
pip-audit
python manage.py compilemessages --ignore "venv" --ignore ".venv"
python manage.py collectstatic --noinput
```

Use the virtualenv Python on Windows:

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe -m pytest
```

## Critical test areas

- OCR parsed data cleanup and manual confirmation.
- Document upload validation and protected download/preview.
- Missing, expired, and expiring document calculations.
- Reminder idempotency and failed email handling.
- Cron token validation and cron limit validation.
- Read-only and staff role permissions.
- Database media storage and backup/restore behavior.
- Translation overrides and DB fallback behavior.

## When a test fails

1. Read the failing assertion before changing code.
2. Check whether the failure protects real business behavior.
3. Add a regression test for the smallest broken flow.
4. Avoid deleting tests unless they assert behavior that is explicitly obsolete.

## CI

GitHub Actions installs system OCR/gettext/backup dependencies, runs Django checks, deploy checks, migration drift check, Django tests, pytest with 70% coverage gate, Ruff, mypy, Bandit, pip-audit, compilemessages, collectstatic, committed pycache detection, and shell script syntax checks. Production secrets are not required because CI uses `legalize_site.settings.test`.
