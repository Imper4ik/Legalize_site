from __future__ import annotations

from django.db import migrations


def backfill_missing_legacy_case_numbers(apps, schema_editor):
    """Preserve an old client-level number only when it maps unambiguously.

    Earlier Case backfills could create one Case per Client without setting
    ``migration_origin``. Such rows were skipped by migration 0099. We only
    copy the historical client number when the Client has exactly one Case and
    no Case-level number is already present.
    """

    Client = apps.get_model("clients", "Client")
    Case = apps.get_model("clients", "Case")

    clients = (
        Client._base_manager.exclude(case_number__isnull=True)
        .exclude(case_number="")
        .order_by("pk")
    )

    for client in clients.iterator(chunk_size=500):
        case_ids = list(
            Case._base_manager.filter(client_id=client.pk)
            .order_by("pk")
            .values_list("pk", flat=True)[:2]
        )
        if len(case_ids) != 1:
            continue

        case_id = case_ids[0]
        Case._base_manager.filter(
            pk=case_id,
            legacy_case_number__in=[None, ""],
            internal_number__in=[None, ""],
            authority_case_number__in=[None, ""],
        ).update(
            legacy_case_number=client.case_number,
            needs_manual_number_check=True,
        )


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0101_alter_case_options_alter_client_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_missing_legacy_case_numbers,
            migrations.RunPython.noop,
        ),
    ]
