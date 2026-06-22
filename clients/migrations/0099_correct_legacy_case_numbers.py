from __future__ import annotations

from django.db import migrations


def correct_legacy_case_numbers(apps, schema_editor):
    Case = apps.get_model("clients", "Case")
    Client = apps.get_model("clients", "Client")
    
    for case in Case.objects.all():
        if case.migration_origin == "legacy_client_backfill":
            client = Client.objects.filter(pk=case.client_id).first()
            if client:
                old_num = getattr(client, "case_number", "") or ""
                # Reset if they haven't been manually changed yet
                if case.internal_number == old_num and case.authority_case_number == old_num:
                    case.legacy_case_number = old_num
                    case.needs_manual_number_check = True
                    case.internal_number = ""
                    case.authority_case_number = ""
                    case.save(update_fields=[
                        "legacy_case_number",
                        "needs_manual_number_check",
                        "internal_number",
                        "authority_case_number",
                    ])


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0098_document_copied_from_document"),
    ]

    operations = [
        migrations.RunPython(correct_legacy_case_numbers, migrations.RunPython.noop),
    ]
