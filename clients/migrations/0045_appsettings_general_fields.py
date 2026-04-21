from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0044_appsettings"),
    ]

    operations = [
        migrations.AddField(
            model_name="appsettings",
            name="contact_email",
            field=models.EmailField(blank=True, default="", max_length=254, verbose_name="Контактный email"),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="contact_phone",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Контактный телефон"),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="default_proxy_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Имя pełnomocnika по умолчанию"),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="office_address",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Одна строка на строку. Используется как общий адрес текущей базы.",
                verbose_name="Адрес офиса",
            ),
        ),
        migrations.AddField(
            model_name="appsettings",
            name="organization_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="Название организации"),
        ),
    ]
