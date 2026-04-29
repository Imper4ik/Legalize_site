# OCR Processing

## Current Flow

Wezwanie uploads are saved as `Document` records. By default, the staff action "upload and recognize" processes OCR inline so the UI can immediately show recognized data for confirmation. Set `ASYNC_OCR_PROCESSING=True` to move OCR to the queue.

When async OCR is enabled, uploads that request OCR create a `DocumentProcessingJob`, and the `process_document_jobs` management command consumes pending jobs:

```text
upload -> DocumentProcessingJob -> process_document_jobs
```

When staff choose OCR with later review, the job is marked `requires_confirmation=True`.
The worker runs `parse_wezwanie`, stores the parsed payload in `document.parsed_data`, sets `document.awaiting_confirmation=True`, and the checklist shows the "Review OCR Data" action. Client fields and notification emails are applied only after staff confirm the recognized values.

For non-confirmation background OCR, the worker applies reliable parsed client fields directly and records retry/failure state on the job.

## Production Recommendation

For higher upload volume, enable `ASYNC_OCR_PROCESSING=True` and run queued OCR outside the request/response path. On Railway, configure a Cron service or Worker to execute:

```bash
python manage.py process_document_jobs --limit N
```

Choose `N` based on the expected upload volume and available CPU. A small recurring batch is safer than letting request workers perform OCR under user traffic.

## Follow-Up

Consider a dedicated always-on worker if OCR volume grows beyond what periodic batches can process comfortably.
