# OCR Processing

## Current Flow

Wezwanie uploads are saved as `Document` records. For the background path, the upload flow creates a `DocumentProcessingJob`, and the `process_document_jobs` management command consumes pending jobs:

```text
upload -> DocumentProcessingJob -> process_document_jobs
```

The worker command runs `parse_wezwanie`, updates OCR status on the document, applies parsed client fields when data is reliable, and records retry/failure state on the job.

The confirmable upload path still parses synchronously when `parse_requested=True` so the UI can immediately show a confirmation payload to staff.

## Production Recommendation

Run queued OCR outside the request/response path. On Railway, configure a Cron service or Worker to execute:

```bash
python manage.py process_document_jobs --limit N
```

Choose `N` based on the expected upload volume and available CPU. A small recurring batch is safer than letting request workers perform OCR under user traffic.

## Follow-Up

Move confirmable OCR parsing to the background job flow once the UI can show an intermediate "processing" state and later reopen the confirmation form when parsing is complete.
