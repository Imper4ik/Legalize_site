[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Deployment

## Mandatory Environment Variables

For production, you must set the `PDF_FONT_PATH` variable with the absolute path to a TrueType/OpenType font file that will be used for PDF generation (e.g., `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Production Hardening Variables

Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` explicitly. Railway deployments may also provide `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_STATIC_URL`; Render deployments may provide `RENDER_EXTERNAL_HOSTNAME`. The app derives host and CSRF entries from these platform variables, but it no longer ships with a hardcoded Railway hostname.

`REDIS_URL` is required in production. Authentication and public-intake limits need Redis atomic increments across workers; `DatabaseCache` remains only a local/degraded fallback. On Railway, `TRUST_RAILWAY_CLIENT_IP` defaults to true when Railway platform variables are present and uses Railway platform `X-Real-IP`. For another trusted proxy, configure `TRUSTED_PROXY_IPS` explicitly.

Runtime OCR preprocessing depends on both `opencv-python-headless` and `numpy`; they are installed from `requirements.txt` during Docker and Railway/Nixpacks builds. The image also needs Tesseract and Poppler binaries, which are installed by the Dockerfile/Nixpacks configuration.

Default production security values are `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`, and `SECURE_HSTS_PRELOAD=True`. Use a real HTTPS custom domain before relying on browser preload behavior.

Sentry tracing is controlled by `SENTRY_TRACES_SAMPLE_RATE`; use `0.1` for normal production traffic unless active debugging requires a temporary increase.

## Backups

Instructions for enabling and restoring backups on Railway can be found in the document: [docs/backups.md](backups.md).

---

# Polski <a name="polski"></a>

# Wdrażanie (Deployment)

## Obowiązkowe Zmienne Środowiskowe

Dla środowiska produkcyjnego należy ustawić zmienną `PDF_FONT_PATH` z bezwzględną ścieżką do pliku czcionki TrueType/OpenType, który będzie używany do generowania plików PDF (np. `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Kopie Zapasowe

Instrukcja włączania i przywracania kopii zapasowych na Railway znajduje się w dokumencie: [docs/backups.md](backups.md).

---

# Русский <a name="русский"></a>

# Развертывание (Deployment)

## Обязательные переменные окружения

Для продакшена необходимо задать переменную `PDF_FONT_PATH` с абсолютным путём к файлу шрифта TrueType/OpenType, который будет использоваться для генерации PDF (например, `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Бэкапы

Инструкция по включению и восстановлению бэкапов на Railway находится в документе: [docs/backups.md](backups.md).


## Persistent media storage on Railway

Local media inside the container is **not durable** and uploaded client documents will disappear after every redeploy.

### Recommended setup: S3-compatible storage
We recommend using S3-compatible storage (AWS S3, Cloudflare R2, Backblaze B2) for larger production workloads.

**Required Environment Variables:**
- `USE_S3_MEDIA_STORAGE=True`
- `AWS_STORAGE_BUCKET_NAME=...`
- `AWS_ACCESS_KEY_ID=...`
- `AWS_SECRET_ACCESS_KEY=...`
- `AWS_S3_ENDPOINT_URL=...` (if not using standard AWS regions)
- `PRIVATE_MEDIA_LOCATION=private`

### Railway PostgreSQL media storage
For a small Railway deployment, uploaded media can be stored directly in PostgreSQL:

- `USE_DATABASE_MEDIA_STORAGE=True`
- `USE_S3_MEDIA_STORAGE=False`
- `DATABASE_MEDIA_TEMP_ROOT=/app/tmp/database_media`
- `DATABASE_MEDIA_FALLBACK_TO_FILE_SYSTEM=true`
- `DATABASE_MEDIA_AUTO_IMPORT_LEGACY_FILES=true`

This stores the actual file bytes in the `database_media_databasemediafile` table, while `clients_document.file` still stores the logical path such as `documents/example.pdf`. Database backups will include uploaded files, so the database will grow faster and remote database backups become more important. This does not recover files that were already lost from ephemeral Railway storage.

If local files still exist on a running instance, copy them into PostgreSQL before relying on DB media storage:

```bash
python manage.py copy_media_to_database_storage --dry-run
python manage.py copy_media_to_database_storage
```

### Alternative: Railway Volumes
Alternatively, use a Railway Volume mounted to `MEDIA_ROOT`. Set:

- `MEDIA_ROOT=/app/media` (or the exact Railway Volume mount path)
- `ALLOW_PRODUCTION_LOCAL_MEDIA=true`

By default, document rows store only file paths. The uploaded file bytes must live in S3-compatible storage, PostgreSQL media storage, or on a mounted persistent Railway Volume. If files were uploaded before persistent media storage was configured and the service was redeployed, those old file bytes cannot be recovered from PostgreSQL alone; upload them again or restore them from an external media backup.

### Security and Diagnostics
- Document downloads are routed through protected Django views with access checks.
- If a physical file is missing from storage (e.g., due to ephemeral storage loss), the system will log a WARNING and show a friendly error message to the staff user instead of a 404 page.
- ZIP exports will include a `MISSING_FILES.txt` report if any documents are missing.
- If production runs with local media and no explicit acknowledgement, project system checks emit an error and block unsafe deployments. Use `USE_DATABASE_MEDIA_STORAGE=True`, `USE_S3_MEDIA_STORAGE=True`, or set `ALLOW_PRODUCTION_LOCAL_MEDIA=true` only after a persistent Railway Volume is mounted to `MEDIA_ROOT`.

