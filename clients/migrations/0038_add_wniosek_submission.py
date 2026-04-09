from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0037_company_alter_payment_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="WniosekSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "document_kind",
                    models.CharField(
                        choices=[("mazowiecki_application", "Mazowiecki application")],
                        default="mazowiecki_application",
                        max_length=64,
                        verbose_name="Document kind",
                    ),
                ),
                ("attachment_count", models.PositiveIntegerField(default=0, verbose_name="Attachment count")),
                ("confirmed_at", models.DateTimeField(auto_now_add=True, verbose_name="Confirmed at")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="wniosek_submissions",
                        to="clients.client",
                        verbose_name="Client",
                    ),
                ),
                (
                    "confirmed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="confirmed_wniosek_submissions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Confirmed by",
                    ),
                ),
            ],
            options={
                "verbose_name": "Wniosek submission",
                "verbose_name_plural": "Wniosek submissions",
                "ordering": ["-confirmed_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="WniosekAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(blank=True, default="", max_length=255, verbose_name="Document type")),
                ("entered_name", models.CharField(max_length=500, verbose_name="Entered name")),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Position")),
                (
                    "submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="clients.wnioseksubmission",
                        verbose_name="Submission",
                    ),
                ),
            ],
            options={
                "verbose_name": "Wniosek attachment",
                "verbose_name_plural": "Wniosek attachments",
                "ordering": ["position", "id"],
            },
        ),
    ]
