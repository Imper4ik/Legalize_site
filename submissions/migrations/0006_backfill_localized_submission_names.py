from django.db import migrations


LOCALIZED_NAMES = {
    "work": {
        "name_ru": "Работа",
        "name_pl": "Praca",
        "name_en": "Work",
    },
    "study": {
        "name_ru": "Учёба",
        "name_pl": "Studia",
        "name_en": "Study",
    },
    "family": {
        "name_ru": "Воссоединение семьи",
        "name_pl": "Łączenie rodzin",
        "name_en": "Family reunification",
    },
}


def backfill_localized_names(apps, schema_editor):
    Submission = apps.get_model("submissions", "Submission")
    for slug, translations in LOCALIZED_NAMES.items():
        submission = Submission.objects.filter(slug=slug).first()
        if submission is None:
            continue
        changed_fields = []
        for field, value in translations.items():
            if not getattr(submission, field):
                setattr(submission, field, value)
                changed_fields.append(field)
        if changed_fields:
            submission.save(update_fields=changed_fields)


class Migration(migrations.Migration):
    dependencies = [
        ("submissions", "0005_document_archived_at_submission_archived_at"),
    ]

    operations = [
        migrations.RunPython(backfill_localized_names, migrations.RunPython.noop),
    ]
