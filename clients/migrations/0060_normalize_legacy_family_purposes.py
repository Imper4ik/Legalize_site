from django.db import migrations


def forwards(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    Client.objects.filter(application_purpose="family_spouse").update(
        application_purpose="family",
        family_role="family_spouse",
    )
    Client.objects.filter(application_purpose="family_child").update(
        application_purpose="family",
        family_role="family_child",
    )


def backwards(apps, schema_editor):
    Client = apps.get_model("clients", "Client")
    Client.objects.filter(
        application_purpose="family",
        family_role="family_spouse",
    ).update(application_purpose="family_spouse")
    Client.objects.filter(
        application_purpose="family",
        family_role="family_child",
    ).update(application_purpose="family_child")


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0059_familygroup_client_family_role_client_sponsor_client_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
