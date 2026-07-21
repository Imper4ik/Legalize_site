# Demo Center

The Demo Center provides a secure, isolated, and visually stunning demonstration environment for presenting the Legalize system. It is designed to populate the system with realistic mock data representing 5 different client journeys for a 5-minute presentation, and allows clean resets afterward.

## Features

1. **Deterministic Presentation Scenarios**: Automatically generates 5 distinct client profiles representing key workflow paths:
   - **Jan Kowalski** (All Documents OK): Work permit application where all checklist documents are uploaded and verified.
   - **Anna Nowak** (Missing Documents): Work permit application missing key documents (e.g., employment contract).
   - **Daria Testowa** (ZUS RCA Wrong Month): Demonstrates period matching and warning notifications for ZUS RCA.
   - **Ivan Demo** (Wezwanie + OCR + Deadline): Demonstrates OCR parsing, awaiting staff confirmation, and dynamic task/reminder generation.
   - **Maria Student** (Waiting after Fingerprints): Demonstrates study application flow waiting for decision after fingerprints.
2. **Safe Sandbox Isolation**:
   - Every generated object is tagged with `is_demo_data=True`.
   - Real email delivery is bypassed (uses Django's `locmem` email backend) to prevent actual messages from being sent to presenters or clients.
   - Separate media files directory config or isolated storage.
3. **Interactive UI**:
   - Modals for inspecting raw OCR extraction results and email notification previews.
   - Direct, deterministic portal access links for the client portal.
4. **Clean Reset**:
   - `Reset demo data` action in the UI or command line deletes all records and media files with `is_demo_data=True` safely, leaving production data completely untouched.

## Configuration

In `legalize_site/settings/base.py`:
- `DEMO_MODE_ENABLED`: Boolean flag to globally enable/disable Demo Center.
- `DEMO_CENTER_MEDIA_ROOT`: Dedicated media root directory for demo documents.

In `.env`:
```env
DEMO_MODE_ENABLED=True
DEMO_CENTER_MEDIA_ROOT=
```

The Demo Center is enabled by default only outside production. Production startup checks reject `DEMO_MODE_ENABLED=True`; keep it disabled on every live service.

## Management Commands

To clean up all demo data from the command line:
```bash
python manage.py clean_demo_data --confirm
```

## Security & Isolation

- **Superuser Access Only**: Access to the Demo Center is strictly restricted to authenticated superusers.
- **Deterministic Onboarding Tokens**: Temporary onboarding/portal links use a cryptographic hash based on the client's database primary key and `settings.SECRET_KEY`, avoiding token collision or DB modifications during presentation.
- **Cascade Cleanup**: Deleting a demo client cascades and cleanly deletes all payments, documents, and reminders, leaving no trace.
