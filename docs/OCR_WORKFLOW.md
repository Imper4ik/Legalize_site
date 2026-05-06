# OCR Workflow

## Upload

Staff uploads documents through the client detail flow. Supported types are PDF, JPG, JPEG, PNG, and WebP. Upload validation checks extension, MIME type, size, PDF integrity, image format, dimensions, and path-like filenames.

For wezwanie-like document types, authorized users can request OCR. The upload creates a `DocumentProcessingJob` and sets the document OCR status to `pending`.

## Processing job

`python manage.py process_document_jobs --limit 50` processes queued jobs. The cron endpoint `/cron/process-document-jobs/` accepts a positive `limit`; values over 100 are clamped to 100.

The worker:

- leases a pending job;
- copies the protected file to a temporary file;
- runs `parse_wezwanie`;
- updates the client only when safe;
- stores safe parsed summary fields;
- clears retry metadata on success;
- retries failed jobs with backoff until `max_attempts`.

## Parser

The parser extracts:

- fingerprints date, display date, time, location;
- ticket number and list name;
- application status code;
- decision date;
- required document codes;
- case number and name only as temporary parser output.

Raw OCR text must not be stored in `Document.parsed_data` after background processing.

## Manual confirmation

When a job requires confirmation, `Document.awaiting_confirmation=True` allows authorized OCR reviewers to fetch parsed data for the confirmation form. This is the only intended temporary PII window.

After `confirm_wezwanie_document`, `parsed_data` is reduced to:

- `confirmed=True`
- `confirmed_fields`
- `pii_scrubbed=True`
- `raw_text_removed=True`

The confirmed values are applied to the client model where business logic expects them.

## PII scrub

`python manage.py scrub_ocr_pii --dry-run` scans non-awaiting documents for:

- `full_name`
- `first_name`
- `last_name`
- `case_number`
- `text`
- `raw_text`

The command removes these keys even if `pii_scrubbed=True` was already present. It never touches documents still awaiting confirmation.

## Troubleshooting

If OCR returns no text, check Tesseract, Poppler, `pdf2image`, `pytesseract`, and uploaded file validity. Runtime dependency warnings appear in `python manage.py check`.
