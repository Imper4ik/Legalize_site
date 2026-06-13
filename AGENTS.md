# Codex Instructions

## Project Context

Legalize_site is a Django CRM for managing legalization workflows for foreigners in Poland. It handles clients, cases, documents, OCR, notifications, deadlines, staff roles, payments, sensitive personal data, encrypted fields, and production deployment.

Before doing broad work, read:

- `README.md`
- `docs/CODEX_CLOUD_HANDOFF.md`
- `docs/local_file_inventory.txt`
- `docs/SECURITY_RODO.md`
- `docs/OCR_WORKFLOW.md`
- `docs/BUSINESS_WORKFLOW.md`
- `docs/TESTING.md`

## Safety Rules

- Treat client data, document files, OCR output, emails, passport data, case numbers, and staff activity as sensitive.
- Do not weaken CSRF, authentication, authorization, object-level permissions, validation, encryption, rate limiting, or production security.
- Do not commit `.env`, `db.sqlite3`, uploaded media, static build output, cache folders, coverage files, or local temp files.
- Prefer small, reviewable changes with tests when touching security, permissions, documents, OCR, notifications, migrations, or encrypted fields.
- Do not invent missing files or behavior. If context is incomplete, say which exact file or module needs inspection.

## Common Commands

- Install development dependencies: `pip install -r requirements-dev.txt`
- Run migrations: `python manage.py migrate`
- Start local server: `python manage.py runserver`
- Run tests: `pytest`
- Run Django checks: `python manage.py check`
- Production checks: `python manage.py check --deploy`
- Process OCR jobs: `python manage.py process_document_jobs`
- Update reminders: `python manage.py update_reminders`

## Architecture Notes

- Core Django project: `legalize_site/`
- Main business app: `clients/`
- Public submission flow: `submissions/`
- Runtime translation tooling: `translations/`
- Custom user model and auth helpers: `users/`
- Database-backed media storage: `database_media/`
- Encrypted field support: `fernet_fields/`
- Project docs: `docs/`
- Templates: `templates/` and app-level `templates/`
- Static assets: `static/`

## Deployment Notes

The repository contains deployment files for Railway and Render: `railway.toml`, `nixpacks.toml`, `render.yaml`, `Dockerfile`, `build.sh`, `start.sh`, and `release.sh`.

For cloud work, configure secrets through the host/provider, not through committed files. Required production values include `SECRET_KEY`, `FERNET_KEYS`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, email settings, `CRON_TOKEN`, and a persistent media strategy such as database media storage or S3-compatible storage.
