# Employer change workflow

Employer data is scoped to a `Case`, not globally to a client. This is important
when one person has several concurrent proceedings.

## Capture points

- Staff can select an existing company or enter a company name/NIP in the case form.
- A client applying for work can enter the employer name and NIP during onboarding.
- If no employer was captured earlier, the MOS fingerprints action asks staff for it.
- Successful company-document OCR uses registry name/NIP/KRS data.
- Successful ZUS OCR uses the extracted employer NIP.

## Conservative review

OCR and client-entered values never overwrite `Case.company`. Identifiers are
compared first; an exact normalized name is only a fallback. A mismatch creates
an `EmployerChangeCandidate` and an unassigned high-priority `StaffTask`, visible
to staff. Reprocessing the same source is idempotent.

Staff can confirm a new employer, mark it as the same employer or an OCR error,
request more information, or defer the decision. Confirmation is transactional,
closes the previous active `CaseEmployerAssignment`, updates the case, creates a
new history row with an optional effective employment date, closes the matching
task, and records an activity event.

Archived, closed, and non-work cases are ignored. Object-level case access is
checked by the review view. RODO anonymization removes employer candidates and
history, clears `Case.company`, and scrubs generated employer-review tasks.

## UI and mobile behavior

The client onboarding page presents employer data as one compact card. Fields
stack on small screens, NIP opens a numeric mobile keyboard, and the copy makes
clear that an unknown employer may be supplied later at fingerprints.

The staff case page shows a side-by-side current/proposed comparison on wider
screens and a vertical comparison on phones. It links to the source document,
accepts the effective change date and a review note, and uses large wrapping
action buttons. The existing company is explicitly shown as unchanged until a
staff member confirms the candidate.

## Deployment

Apply migration `clients.0124_employer_change_tracking` before starting workers.
Deploy web and OCR worker code from the same release so an older worker does not
process documents against a newer schema.

## Product decisions still worth making

- Notifications are in-app staff tasks. Email, Teams, or Slack escalation should
  be a separate opt-in channel with its own deduplication and delivery audit.
- Name-only matching is deliberately strict. Fuzzy matching can reduce manual
  work but should only rank candidates; it should not auto-confirm a change.
- The current operational roles (`Admin`, `Manager`, `Staff`) may all review a
  candidate. A buyer may prefer a separate employer-review permission or
  two-person approval for high-risk cases.
- Existing duplicate `Company` rows are not merged automatically. A controlled
  cleanup tool should precede any future database-level unique constraints on
  NIP, REGON, or KRS.
