# Wezwanie and fingerprint follow-up automation

## Objectives
- Inform clients immediately about their fingerprint appointment (date, time, location) and required documents once we receive a *Wezwanie* summons.
- After the fingerprint visit, use the official confirmation document to identify any missing items and send the client a focused reminder.
- Keep a clear audit trail (what was received, when notices were sent, remaining gaps) while minimizing manual data entry.

## Proposed flow
1. **Inbound summons (Wezwanie) intake**
   - Monitor the shared inbox used for immigration correspondence and auto-file new *Wezwanie* PDFs to the client’s record (matching by case number or email).
   - Parse the summons for: case number, client name, appointment date/time/location, and the checklist of documents requested.
   - Store parsed fields in structured attributes on the `Document`/`Case` model and keep the original PDF attached for reference.

2. **Appointment notification to the client**
   - Immediately send a templated email that includes:
     - Appointment details (date/time/location) pulled from the parsed *Wezwanie*.
     - The list of documents to bring, rendered as a checklist.
     - A link to confirm receipt and ask questions.
   - Record the send status and body snapshot so staff can verify what the client saw.

3. **Fingerprint confirmation (post-visit) intake**
   - Watch the same inbox for the post-fingerprint confirmation letter that lists delivered vs. outstanding items.
   - Parse the document to extract the visit date and the set of documents still missing.
   - Update the case record: mark the fingerprint step as completed and register outstanding documents with due dates (if provided).

4. **Automated missing-document reminder**
   - Send an email summarizing only the missing items, with clear instructions on how to submit them (upload link or office drop-off) and any deadlines from the letter.
   - If nothing is missing, record a “no outstanding documents” note and skip the reminder.

5. **Follow-up and visibility**
   - Schedule a lightweight daily task to re-check outstanding documents and re-send reminders at sensible intervals (e.g., 3 and 7 days before deadline, then weekly) until items are marked received.
   - Surface status in the staff dashboard: latest *Wezwanie* info, fingerprint confirmation, outstanding docs, and email history.

6. **Error handling and safeguards**
   - Flag uncertain matches (e.g., ambiguous case number/name) for manual review instead of auto-sending.
   - Keep all parsed values editable by staff and capture original documents so corrections are easy.
   - Log parsing failures and email delivery issues with alerts to the team channel.

## Why this is efficient
- **Single intake channel** (shared inbox) removes manual uploads and ensures both summons and post-fingerprint letters are handled the same way.
- **Structured parsing** keeps critical dates and document lists machine-readable, enabling instant emails and dashboard updates.
- **Targeted reminders** focus only on missing items, reducing noise for clients and staff.
- **Auditable trail** links each notification to the source document and stored fields, simplifying compliance and client support.
