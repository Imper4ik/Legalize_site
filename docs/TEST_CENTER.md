# Test Center

The Test Center is a built-in diagnostic and end-to-end (E2E) testing framework that allows superusers to run scenarios on demand from the admin interface. It validates email notification rules, workflow transitions, permissions, and OCR processing pipelines.

## Modes

The Test Center supports the following scenario modes (defined in `SCENARIO_GROUPS`):

- `smoke`: Basic checks verifying onboarding link resolution, test data flags, and basic workflow stage transitions.
- `email`: Validates notification templates, formatting, and delivery status logging.
- `zus`: Checks calculations for missing ZUS RCA months and validity periods.
- `ocr`: Tests parsing and approval flow of Wezwanie files.
- `ocr-fixtures`: **(New)** Runs the actual E2E parsing and document validation pipeline on specific fixture files (`wezwanie_clean.pdf`, `zus_rca_good.pdf`, `zus_rca_wrong_month.pdf`, `unreadable_scan.jpg`) under mocked text extraction to verify system behavior without local Tesseract/Poppler dependencies.
- `documents`: Tests access rules for document download and preview.
- `permissions`: Validates roles, groups, and staff action authorization.
- `workflow`: Exercises the full client onboarding and transition lifecycle.
- `full`: Runs all E2E scenario groups sequentially.

## Configuration

In `legalize_site/settings/base.py`:
- `ENABLE_TEST_CENTER`: Globally enables/disables Test Center.
- `TEST_CENTER_MEDIA_ROOT`: Dedicated media root directory for test documents.

In `.env`:
```env
ENABLE_TEST_CENTER=True
TEST_CENTER_MEDIA_ROOT=
```

## Running Scenarios

### Via UI
1. Navigate to `/test-center/` as a superuser.
2. Select the desired mode (e.g. `ocr-fixtures`).
3. Click `Run Scenarios`.

### Via Management Command
```bash
python manage.py run_e2e_scenarios --mode ocr-fixtures
```
