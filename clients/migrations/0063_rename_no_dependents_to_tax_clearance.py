from __future__ import annotations

from django.db import migrations


OLD_VALUES = {
    "pl": "Oświadczenie o braku osób na utrzymaniu w Polsce",
    "ru": "Заявление об отсутствии иждивенцев в Польше",
    "en": "Statement of no dependents in Poland",
}

NEW_VALUES = {
    "pl": "Zaświadczenie o niezaleganiu w podatkach",
    "ru": "Справка об отсутствии задолженности по налогам",
    "en": "Certificate of no tax arrears",
}


def rename_no_dependents_requirement(apps, schema_editor):
    DocumentRequirement = apps.get_model("clients", "DocumentRequirement")

    queryset = DocumentRequirement.objects.filter(document_type="no_dependents_statement")
    for requirement in queryset.iterator():
        update_fields = []
        for lang, old_value in OLD_VALUES.items():
            field_name = f"custom_name_{lang}"
            current_value = getattr(requirement, field_name, None)
            if current_value in (None, "", old_value):
                setattr(requirement, field_name, NEW_VALUES[lang])
                update_fields.append(field_name)

        # The base name was historically populated from the same old label in some databases.
        if requirement.custom_name in (None, "", OLD_VALUES["pl"]):
            requirement.custom_name = NEW_VALUES["pl"]
            update_fields.append("custom_name")

        if update_fields:
            requirement.save(update_fields=update_fields)


def reverse_rename_no_dependents_requirement(apps, schema_editor):
    DocumentRequirement = apps.get_model("clients", "DocumentRequirement")

    queryset = DocumentRequirement.objects.filter(document_type="no_dependents_statement")
    for requirement in queryset.iterator():
        update_fields = []
        for lang, new_value in NEW_VALUES.items():
            field_name = f"custom_name_{lang}"
            if getattr(requirement, field_name, None) == new_value:
                setattr(requirement, field_name, OLD_VALUES[lang])
                update_fields.append(field_name)

        if requirement.custom_name == NEW_VALUES["pl"]:
            requirement.custom_name = OLD_VALUES["pl"]
            update_fields.append("custom_name")

        if update_fields:
            requirement.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0062_alter_client_user_set_null"),
    ]

    operations = [
        migrations.RunPython(rename_no_dependents_requirement, reverse_rename_no_dependents_requirement),
    ]
