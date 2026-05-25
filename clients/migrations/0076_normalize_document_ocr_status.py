from __future__ import annotations

from django.db import migrations


def normalize_completed_ocr_status(apps, schema_editor):
    Document = apps.get_model("clients", "Document")
    Document.objects.filter(ocr_status="completed").update(ocr_status="success")


def restore_completed_ocr_status(apps, schema_editor):
    # The current model does not expose "completed" as a valid choice. Keep reverse
    # migrations data-safe instead of recreating invalid status values.
    return None


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0075_alter_documentprocessingjob_job_type"),
    ]

    operations = [
        migrations.RunPython(normalize_completed_ocr_status, restore_completed_ocr_status),
    ]