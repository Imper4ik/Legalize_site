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
            sql="""
            DO $$
            DECLARE idx record;
            BEGIN
                FOR idx IN
                    SELECT schemaname, indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname LIKE 'submissions_submission_slug%'
                LOOP
                    EXECUTE 'DROP INDEX IF EXISTS '
                        || quote_ident(idx.schemaname)
                        || '.'
                        || quote_ident(idx.indexname);
                END LOOP;
            END$$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name='submission',
            name='slug',
            field=models.SlugField(max_length=64, null=True, blank=True, unique=False, verbose_name='Слаг основания'),
        ),
        migrations.RunPython(populate_slugs, migrations.RunPython.noop),
        migrations.RunPython(ensure_defaults, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='submission',
            name='slug',
            field=models.SlugField(max_length=64, unique=True, verbose_name='Слаг основания'),
        ),
    ]
