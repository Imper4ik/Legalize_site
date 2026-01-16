from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0032_populate_document_translations"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="awaiting_confirmation",
            field=models.BooleanField(default=False, verbose_name="Ожидает подтверждения"),
        ),
    ]
