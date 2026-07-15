from __future__ import annotations

from django.db import migrations


def repair_ocr_name_mismatch_flags(apps, schema_editor) -> None:
    """Separate legacy generic OCR warnings from actual name warnings."""

    Document = apps.get_model("clients", "Document")
    queryset = Document.objects.filter(ocr_name_mismatch=True).only("pk", "parsed_data")
    to_clear: list[int] = []
    for document in queryset.iterator(chunk_size=500):
        parsed_data = document.parsed_data
        if isinstance(parsed_data, dict) and parsed_data.get("has_name_mismatch") is False:
            to_clear.append(document.pk)
        if len(to_clear) >= 500:
            Document.objects.filter(pk__in=to_clear).update(ocr_name_mismatch=False)
            to_clear.clear()
    if to_clear:
        Document.objects.filter(pk__in=to_clear).update(ocr_name_mismatch=False)


class Migration(migrations.Migration):
    dependencies = [("clients", "0124_employer_change_tracking")]

    operations = [
        migrations.RunPython(repair_ocr_name_mismatch_flags, migrations.RunPython.noop),
    ]
