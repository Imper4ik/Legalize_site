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
                -- Drop any pre-existing index or constraint that references the slug field
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'submissions_submission_slug_key'
                        AND conrelid = 'submissions_submission'::regclass
                ) THEN
                    EXECUTE 'ALTER TABLE submissions_submission DROP CONSTRAINT IF EXISTS submissions_submission_slug_key';
                END IF;

                FOR idx IN
                    SELECT n.nspname AS schemaname, c.relname AS indexname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind = 'i'
                      AND c.relname LIKE 'submissions_submission_slug%'
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
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE submissions_submission "
                        "ADD COLUMN IF NOT EXISTS slug varchar(64);"
                    ),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
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
            ],
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
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = 'submissions_submission_slug_dcff9617_like'
                              AND c.relkind = 'i'
                        ) THEN
                            CREATE UNIQUE INDEX submissions_submission_slug_dcff9617_like
                                ON submissions_submission (slug varchar_pattern_ops);
                        END IF;

                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'submissions_submission_slug_key'
                              AND conrelid = 'submissions_submission'::regclass
                        ) THEN
                            ALTER TABLE submissions_submission
                                ADD CONSTRAINT submissions_submission_slug_key
                                UNIQUE USING INDEX submissions_submission_slug_dcff9617_like;
                        END IF;
                    END$$;
                    """,
                    reverse_sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1 FROM pg_constraint
                            WHERE conname = 'submissions_submission_slug_key'
                              AND conrelid = 'submissions_submission'::regclass
                        ) THEN
                            ALTER TABLE submissions_submission DROP CONSTRAINT submissions_submission_slug_key;
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = 'submissions_submission_slug_dcff9617_like'
                              AND c.relkind = 'i'
                        ) THEN
                            DROP INDEX submissions_submission_slug_dcff9617_like;
                        END IF;
                    END$$;
                    """,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='submission',
                    name='slug',
                    field=models.SlugField(max_length=64, unique=True, verbose_name='Слаг основания'),
                ),
            ],
        ),
    ]
