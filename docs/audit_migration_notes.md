# Audit migration notes

## Duplicate `clients` migration numbers

The `clients` app intentionally contains two historical `0052_*` migrations and two historical `0053_*` migrations:

- `0052_alter_emailcampaign_error_details_and_more.py`
- `0052_alter_client_options_client_client_staff_status_idx_and_more.py`
- `0053_alter_emailcampaign_recipient_emails.py`
- `0053_document_parsed_data_and_more.py`

These migrations are already part of the project history and may have been applied in deployed environments. Do **not** rename or rewrite them in place. Django resolves the graph through the merge migration (`0055_merge_20260427_1920`).

Operational checks:

```bash
python manage.py showmigrations clients --plan
python manage.py migrate --plan
python manage.py migrate --check
```

CI should keep running `makemigrations --check --dry-run` and `migrate --check` to catch future migration drift without rewriting historical migration files.
