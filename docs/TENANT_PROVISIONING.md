# Tenant provisioning (instance-per-firm)

This app runs **one isolated instance per firm**: each tenant gets its own
deployment, its own database, and its own `AppSettings`. Data is physically
isolated between firms — the strongest posture for RODO. There is no shared
multi-tenant database; do not point two firms at the same `DATABASE_URL`.

## Standing up a new firm

1. **Provision infrastructure**
   - New service from this repo (Railway/Render/etc.) + a dedicated PostgreSQL.
   - Optional Redis; without `REDIS_URL` rate limiting uses the PostgreSQL cache.
   - Persistent media: `USE_S3_MEDIA_STORAGE=True` (own bucket per firm) or
     `USE_DATABASE_MEDIA_STORAGE=True`.

2. **Core environment variables** (see `.env.example` for the full list)
   - `SECRET_KEY`, `FERNET_KEYS` — **unique per firm** (never share encryption keys across tenants).
   - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `APP_ENV=production`.
   - `DATABASE_URL` — the firm's own database.
   - Superuser bootstrap: `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`.

3. **Tenant identity + RODO requisites** (`TENANT_*`, consumed by `configure_tenant`)
   - `TENANT_ORG_NAME`, `TENANT_CONTACT_EMAIL`, `TENANT_CONTACT_PHONE`, `TENANT_OFFICE_ADDRESS`, `TENANT_DEFAULT_PROXY`
   - Data controller (art. 13): `TENANT_LEGAL_ENTITY_NAME`, `TENANT_NIP`, `TENANT_REGON`, `TENANT_KRS`, `TENANT_LEGAL_ADDRESS`, `TENANT_REPRESENTATIVE`, `TENANT_DPO_CONTACT`
   - Policy/consent: `TENANT_PRIVACY_POLICY_VERSION`, `TENANT_DATA_RETENTION`

4. **Deploy**, then run migrations and seed the tenant settings:
   ```bash
   python manage.py migrate --noinput
   python manage.py compilemessages   # required for translations (PL/EN/RU)
   python manage.py configure_tenant  # seeds AppSettings from TENANT_* vars
   ```
   `configure_tenant` is idempotent — safe to run on every deploy. Only fields
   whose `TENANT_*` variable is set are applied, so it never clears values a
   firm later edits in the UI. Use `--dry-run` to preview.

5. **Verify**
   - Log in as the superuser; confirm the org name and data-controller block on
     `/settings/templates/` and the public notice at `/privacy/`.
   - Confirm no data from any other firm is visible (separate DB guarantees it).

## De-provisioning

To offboard a firm: take a final database + media backup, hand over any export
the contract requires, then delete the service, database, and media bucket. No
other tenant is affected.

## When to move to shared multi-tenancy

Instance-per-firm scales operationally to roughly dozens of tenants. If you need
self-serve signup or many small tenants on one deployment, that requires a
shared multi-tenant redesign (an `Organization` model, tenant-scoped queries on
every model, per-tenant `AppSettings`, and billing) — a separate, larger effort.
