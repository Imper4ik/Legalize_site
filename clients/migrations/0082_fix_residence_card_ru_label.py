from django.db import migrations


BAD_RESIDENCE_CARD_LABELS = ["", "Карта пребывания", "Карта проживания"]


def fix_residence_card_ru_label(apps, schema_editor):
    DocumentRequirement = apps.get_model("clients", "DocumentRequirement")
    DocumentRequirement.objects.filter(
        document_type="residence_card",
        custom_name_ru__in=BAD_RESIDENCE_CARD_LABELS,
    ).update(custom_name_ru="Карта побыту")


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0081_client_no_self_sponsor"),
    ]

    operations = [
        migrations.RunPython(fix_residence_card_ru_label, migrations.RunPython.noop),
    ]
