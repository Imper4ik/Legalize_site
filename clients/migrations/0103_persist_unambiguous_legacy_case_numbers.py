from __future__ import annotations

from django.db import migrations


def persist_unambiguous_legacy_case_numbers(apps, schema_editor):
    """Repair legacy Case rows skipped by encrypted-field SQL lookups.

    We only copy a historical Client.case_number when the Client has exactly
    one Case and all Case-level number fields are blank. That preserves the
    number for display and manual review without guessing whether it belongs
    in the internal or authority-number field.
    """

    Client = apps.get_model("clients", "Client")
    Case = apps.get_model("clients", "Case")

    for client in Client._base_manager.order_by("pk").iterator(chunk_size=250):
        legacy_number = str(getattr(client, "case_number", "") or "").strip()
        if not legacy_number:
            continue

        cases = list(
            Case._base_manager.filter(client_id=client.pk)
            .order_by("pk")[:2]
        )
        if len(cases) != 1:
            continue

        case = cases[0]
        if any(
            str(value or "").strip()
            for value in (
                getattr(case, "internal_number", ""),
                getattr(case, "authority_case_number", ""),
                getattr(case, "legacy_case_number", ""),
            )
        ):
            continue

        case.legacy_case_number = legacy_number
        case.needs_manual_number_check = True
        case.save(update_fields=["legacy_case_number", "needs_manual_number_check"])


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0102_backfill_missing_legacy_case_numbers"),
    ]

    operations = [
        migrations.RunPython(
            persist_unambiguous_legacy_case_numbers,
            migrations.RunPython.noop,
        ),
    ]
