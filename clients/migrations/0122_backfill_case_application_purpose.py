# Data migration: complete the case-first purpose migration.
#
# Historically the document-requirement purpose lived on Client and
# purpose_for_case() fell back to it for clients with exactly one case. This
# backfill copies the client purpose onto that single case so the code-level
# fallback can be removed and Case becomes the only owner of the process
# purpose (spec §4). Multi-case clients are intentionally left as-is: their
# empty-purpose cases must get an explicit purpose via the portal/staff flow.

from django.db import migrations

VALID_FAMILY_ROLES = {"sponsor", "family_spouse", "family_child"}


def backfill_case_application_purpose(apps, schema_editor):
    Case = apps.get_model("clients", "Case")
    Client = apps.get_model("clients", "Client")

    clients = Client.objects.exclude(application_purpose="").exclude(application_purpose__isnull=True)
    for client in clients.iterator():
        cases = list(
            Case.objects.filter(client_id=client.pk).only("id", "application_purpose", "family_role")[:2]
        )
        if len(cases) != 1:
            continue
        case = cases[0]
        if case.application_purpose:
            continue
        updates = {"application_purpose": str(client.application_purpose)}
        client_role = str(getattr(client, "family_role", "") or "")
        if (
            updates["application_purpose"] == "family"
            and not case.family_role
            and client_role in VALID_FAMILY_ROLES
        ):
            updates["family_role"] = client_role
        Case.objects.filter(pk=case.pk, application_purpose="").update(**updates)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0121_backfill_reminder_case"),
    ]

    operations = [
        migrations.RunPython(backfill_case_application_purpose, noop_reverse),
    ]
