[English](#english) | [Polski](#polski) | [Русский](#русский)

---

# English <a name="english"></a>

# Deployment

## Mandatory Environment Variables

For production, you must set the `PDF_FONT_PATH` variable with the absolute path to a TrueType/OpenType font file that will be used for PDF generation (e.g., `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`).

## Production Hardening Variables

Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` explicitly. Railway deployments may also provide `RAILWAY_PUBLIC_DOMAIN` and `RAILWAY_STATIC_URL`; Render deployments may provide `RENDER_EXTERNAL_HOSTNAME`. The app derives host and CSRF entries from these platform variables, but it no longer ships with a hardcoded Railway hostname.

Set `REDIS_URL` in production so rate limiting uses Django `RedisCache` across workers. Without `REDIS_URL`, Django falls back to local cache and a system check warning is emitted.

Default HSTS production values are `SECURE_HSTS_SECONDS=31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS=False`, and `SECURE_HSTS_PRELOAD=False`. Override them via env only after confirming the domain policy. Do not enable preload until the domain is ready for browser preload submission.

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
We recommend using S3-compatible storage (AWS S3, Cloudflare R2, Backblaze B2).

**Required Environment Variables:**
- `USE_S3_MEDIA_STORAGE=True`
- `AWS_STORAGE_BUCKET_NAME=...`
- `AWS_ACCESS_KEY_ID=...`
- `AWS_SECRET_ACCESS_KEY=...`
- `AWS_S3_ENDPOINT_URL=...` (if not using standard AWS regions)
- `PRIVATE_MEDIA_LOCATION=private`

### Alternative: Railway Volumes
Alternatively, use a Railway Volume mounted to the `MEDIA_ROOT` (default `media/`) and backup directories.

### Security and Diagnostics
- Document downloads are routed through protected Django views with access checks.
- If a physical file is missing from storage (e.g., due to ephemeral storage loss), the system will log a WARNING and show a friendly error message to the staff user instead of a 404 page.
- ZIP exports will include a `MISSING_FILES.txt` report if any documents are missing.
- If production runs with local media and no explicit acknowledgement (`ALLOW_PRODUCTION_LOCAL_MEDIA=true`), project system checks emit a warning.

