from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Submission = apps.get_model('submissions', 'Submission')
    for submission in Submission.objects.all():
        if submission.slug:
            continue
        base_slug = slugify(submission.name, allow_unicode=True) or 'submission'
        candidate = base_slug
        counter = 1
        while Submission.objects.filter(slug=candidate).exclude(pk=submission.pk).exists():
            counter += 1
            candidate = f"{base_slug}-{counter}"
        submission.slug = candidate
        submission.save(update_fields=['slug'])


def ensure_defaults(apps, schema_editor):
    Submission = apps.get_model('submissions', 'Submission')
    defaults = [
        ('study', 'Учёба'),
        ('work', 'Работа'),
        ('family', 'Воссоединение семьи'),
    ]
    for slug, name in defaults:
        Submission.objects.get_or_create(slug=slug, defaults={'name': name})


class Migration(migrations.Migration):

    dependencies = [
        ('submissions', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP INDEX IF EXISTS submissions_submission_slug_dcff9617_like",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name='submission',
            name='slug',
            field=models.SlugField(
                max_length=64,
                null=True,
                blank=True,
                unique=False,
                db_index=False,
                verbose_name='Слаг основания',
            ),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.RunPython(ensure_defaults, migrations.RunPython.noop),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE submissions_submission "
                "ALTER COLUMN slug SET NOT NULL;"
            ),
            reverse_sql=(
                "ALTER TABLE submissions_submission "
                "ALTER COLUMN slug DROP NOT NULL;"
            ),
        ),
        migrations.AlterField(
            model_name='submission',
            name='slug',
            field=models.SlugField(max_length=64, unique=True, verbose_name='Слаг основания'),
        ),
    ]
