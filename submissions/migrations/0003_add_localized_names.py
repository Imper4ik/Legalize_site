from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0002_add_slug_submission'),
    ]

    operations = [
        migrations.AddField(
            model_name='submission',
            name='name_en',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Название основания (EN)'),
        ),
        migrations.AddField(
            model_name='submission',
            name='name_pl',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Название основания (PL)'),
        ),
        migrations.AddField(
            model_name='submission',
            name='name_ru',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='Название основания (RU)'),
        ),
    ]
