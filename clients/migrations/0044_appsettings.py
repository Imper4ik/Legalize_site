from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0043_emailcampaign_filters_snapshot_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "mazowiecki_office_template",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Одна строка на строку. Подставляется по умолчанию в шаблон wniosek mazowiecki для всей базы.",
                        verbose_name="Mazowiecki: адрес urzedu",
                    ),
                ),
                (
                    "mazowiecki_proxy_template",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Одна строка на строку. Подставляется по умолчанию в шаблон wniosek mazowiecki для всей базы.",
                        verbose_name="Mazowiecki: pelnomocnik",
                    ),
                ),
            ],
            options={
                "verbose_name": "Настройки приложения",
                "verbose_name_plural": "Настройки приложения",
            },
        ),
    ]
