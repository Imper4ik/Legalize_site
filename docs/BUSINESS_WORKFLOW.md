# Business Workflow

Legalize_site models a small immigration CRM for residence-permit work in Poland. The workflow is intentionally conservative: staff can move a case forward, but the system avoids destructive automation and keeps OCR-derived data reviewable.

## Case stages

1. `new_client`: client record exists, basis and language are selected.
2. `document_collection`: required document checklist is active.
3. `application_submitted`: application was submitted to the office.
4. `fingerprints`: appointment is scheduled or expected.
5. `waiting_decision`: fingerprints are done and the case waits for a decision.
6. `decision_received`: decision date is known.
7. `closed`: case is finished.

## Legal basis and family cases

Supported high-level purposes are work, study, and family reunification. Spouse and child cases stay under family reunification through `family_role`; they are not separate business purposes. The document checklist can still resolve to `family_spouse` or `family_child` internally so the required document set stays precise.

## Documents

Required documents come from `DocumentRequirement` records with a fallback catalog in constants. A checklist item is complete when a document is uploaded or a submitted Wniosek attachment covers that code. Uploaded documents use UUID storage names so original filenames do not leak PII.

Important document states:

- Uploaded but not verified: staff still needs to check it.
- Verified: staff accepted it for the case.
- Missing: required by checklist and not uploaded/submitted.
- Expired or expiring soon: based on `expiry_date`.
- OCR awaiting review: wezwanie OCR parsed data exists and needs confirmation.

## Wezwanie and OCR effect

Wezwanie OCR can detect fingerprints appointments, ticket/list fields, decision dates, application status code, and required document codes. Background OCR applies safe workflow fields to the client and scrubs PII from `Document.parsed_data`. Manual OCR review may temporarily show parsed PII to authorized users; confirmation then writes only a safe summary back to `parsed_data`.

## Reminders

Daily reminders cover overdue payments, expiring/expired documents, missing documents for clients waiting after fingerprints, and missing ZUS RCA months. Email idempotency keys prevent duplicate messages for the same logical reminder window.

## Roles

- Admin: full operational access.
- Manager: client, document, payment, reminders, email, and reporting workflows.
- Staff: client and document work without destructive admin-only actions.
- ReadOnly: view-only CRM access.
- Translator: translation tooling only.

## Demo path

Use `python manage.py seed_demo_data --confirm` in a non-production environment. It creates fake clients across collection, waiting-decision, and decision-received stages, plus an OCR awaiting review example, expired document, payment, reminder, and email log.
