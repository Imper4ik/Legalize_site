# Codex Cloud Handoff

Generated for future cloud work on 2026-06-07.

## Purpose

This file preserves local project context so Codex cloud can understand the repository without relying on local-only memory. The complete local file inventory is in `docs/local_file_inventory.txt`.

## Current Project

- Name: `Legalize_site`
- Type: Django CRM
- Main purpose: manage legalization workflows for foreigners in Poland, including clients, cases, documents, OCR, notifications, deadlines, staff roles, sensitive data, encrypted fields, and deployment.
- Local workspace observed: `E:\Anigravity\Legalize_site`
- Git state at handoff time: clean working tree for tracked files.
- Tracked file count observed before adding this handoff: 600.
- Cloud source inventory count after adding handoff files: see `docs/local_file_inventory.txt`.

## Main Areas

- `legalize_site/`: Django project settings, URLs, runtime helpers, checks, observability, security, cron views, backup utilities, and mail helpers.
- `clients/`: primary CRM app. Contains models, views, services, use cases, forms, templates, tests, management commands, security helpers, and migrations.
- `submissions/`: external/public submission workflows, forms, views, URLs, tests, and migrations.
- `translations/`: translation runtime, middleware, import/export commands, templates, static overlay, tests, and migrations.
- `users/`: custom user model, auth-related forms/views/adapters, admin, and migrations.
- `database_media/`: database-backed file storage models, storage backend, commands, and tests.
- `fernet_fields/`: encrypted field implementation and tests.
- `docs/`: business, security, OCR, testing, backup, deployment, and workflow documentation.
- `templates/`: project-level Django templates, account/social/admin templates, and shared includes.
- `static/`: project CSS/JS/images and client static assets.
- `locale/`: PL/EN/RU translation catalogs.

## Important Existing Docs

- `README.md`: feature summary, deployment notes, local development, cron, production checklist, and demo scenario.
- `docs/SECURITY_RODO.md`: security and personal-data guidance.
- `docs/OCR_WORKFLOW.md`: OCR workflow guidance.
- `docs/BUSINESS_WORKFLOW.md`: business workflow guidance.
- `docs/TESTING.md`: testing strategy.
- `docs/deployment.md`, `docs/deploy.md`, `docs/RAILWAY_DEPLOYMENT.md`: deployment notes.
- `audit_results.md` and `implementation_plan.md`: existing audit/planning artifacts.

## Cloud Migration Notes

Use GitHub or another Git remote as the source of truth for Codex cloud. Local-only files are not automatically available in cloud tasks unless they are committed or otherwise uploaded.

Do not upload or commit secrets or generated runtime data:

- `.env`
- `db.sqlite3`
- `.coverage`
- `.mypy_cache/`
- `.pytest_cache/`
- `.ruff_cache/`
- `__pycache__/`
- `media/`
- `staticfiles/`
- `tmp/`
- `scratch/`
- `generated_media_test/`
- compiled `*.mo` files unless intentionally needed

For cloud deployment or cloud Codex work, replace those local-only items with provider configuration:

- Production secrets in environment variables.
- PostgreSQL via `DATABASE_URL`.
- Persistent media via `USE_DATABASE_MEDIA_STORAGE=True` or S3-compatible storage.
- Cron/background jobs through provider scheduler, external scheduler, or the existing automation loop.
- Fresh migrations and optional safe demo data instead of local SQLite data.

## Expected Setup Commands

```bash
pip install -r requirements-dev.txt
python manage.py migrate
pytest
```

Production checks:

```bash
python manage.py check --deploy
```

Useful management commands:

```bash
python manage.py process_document_jobs
python manage.py update_reminders
python manage.py process_email_campaigns
python manage.py db_backup
python manage.py seed_demo_data --confirm
```

## Deployment Files

- `Dockerfile`
- `nixpacks.toml`
- `railway.toml`
- `render.yaml`
- `build.sh`
- `start.sh`
- `release.sh`

## High-Risk Areas To Treat Carefully

- Object-level permissions and staff/client access in `clients/views/`, `clients/services/permissions.py`, and `clients/models/permissions.py`.
- Document upload, preview, download, OCR, and deletion flows in `clients/views/documents.py`, `clients/services/document_workflow.py`, and related models/tests.
- Encryption and key rotation in `fernet_fields/`, `clients/security/encrypted.py`, and `legalize_site/management/commands/rotate_fernet_fields.py`.
- Cron endpoints and background tasks in `legalize_site/cron_views.py`, `clients/management/commands/`, and `clients/use_cases/`.
- Production settings in `legalize_site/settings/production.py` and deployment scripts.
- Migrations in apps with sensitive or high-volume data: `clients/`, `submissions/`, `translations/`, `database_media/`, and `users/`.

## Recommended Cloud Workflow

1. Push the repository to GitHub without local secrets or runtime artifacts.
2. Configure Codex cloud against the GitHub repository.
3. Ensure `AGENTS.md`, this handoff file, and `docs/local_file_inventory.txt` are committed.
4. Configure cloud/deployment environment variables separately.
5. Ask Codex cloud to work in branches and open pull requests.
6. Review diffs and tests before merging.
