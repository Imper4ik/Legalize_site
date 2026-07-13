# OCR Processing

## Current Flow

Two kinds of OCR run on uploads, with different execution defaults:

- **Auto-recognition** (passport, ZUS RCA, rental, insurance, company documents)
  triggers on every matching upload — including client portal uploads. Since
  `ASYNC_AUTO_OCR_PROCESSING=True` (the default in production), these create a
  `DocumentProcessingJob` and return immediately; tesseract never runs inside a
  web request. The queue is drained by the in-process automation loop
  (`run_background_automation_loop`, started by `start.sh`) or by the external
  `/cron/process-document-jobs/` webhook.
- **Interactive wezwanie parse** (staff clicked "upload and recognize") stays
  synchronous so the modal can immediately show recognized fields for
  confirmation. Set the global `ASYNC_OCR_PROCESSING=True` to queue this too.

```text
upload -> DocumentProcessingJob -> automation loop / cron -> process_document_jobs
```

When staff choose OCR with later review, the job is marked `requires_confirmation=True`.
The worker runs `parse_wezwanie`, stores the parsed payload in `document.parsed_data`,
sets `document.awaiting_confirmation=True`, and the checklist shows the "Review OCR
Data" action. Client fields and notification emails are applied only after staff
confirm the recognized values.

For non-confirmation background OCR, the worker applies reliable parsed client fields
directly and records retry/failure state on the job.

Development and test settings pin `ASYNC_AUTO_OCR_PROCESSING=False` (inline OCR for
instant feedback / deterministic tests); async-pipeline tests opt in with
`override_settings`.

## Production Recommendation

The default contour needs no extra infrastructure: the web service's automation loop
processes queued jobs every cycle. For higher volume, disable the in-process loop
(`ENABLE_BACKGROUND_AUTOMATION_LOOP=false`) and run a dedicated worker or a cron
schedule executing:

```bash
python manage.py process_document_jobs --limit N
```

Choose `N` based on the expected upload volume and available CPU. A small recurring
batch is safer than letting request workers perform OCR under user traffic.

## Follow-Up

Consider a dedicated always-on worker if OCR volume grows beyond what periodic batches
can process comfortably.
