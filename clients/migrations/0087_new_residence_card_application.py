import fernet_fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0086_test_center_zus_mode"),
    ]

    operations = [
        migrations.AddField(
            model_name="mosapplicationdata",
            name="new_residence_card_application_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Not provided"),
                    ("yes", "Tak / Да"),
                    ("no", "Nie / Нет"),
                    ("unknown", "Nie wiem / Не знаю"),
                ],
                default="",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="mosapplicationdata",
            name="new_residence_card_case_number",
            field=fernet_fields.EncryptedTextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="mosapplicationdata",
            name="new_residence_card_submitted_at",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="mosapplicationdata",
            name="new_residence_card_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mosapplicationdata",
            name="new_residence_card_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
