# Generated manually to support staff log list filters.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0068_clientactivity_metadata_clientactivity_summary"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="emaillog",
            index=models.Index(fields=["delivery_status", "-sent_at"], name="emaillog_status_sent_idx"),
        ),
        migrations.AddIndex(
            model_name="emaillog",
            index=models.Index(fields=["-sent_at"], name="emaillog_sent_idx"),
        ),
        migrations.AddIndex(
            model_name="clientactivity",
            index=models.Index(fields=["actor", "-created_at"], name="activity_actor_created_idx"),
        ),
        migrations.AddIndex(
            model_name="clientactivity",
            index=models.Index(fields=["-created_at"], name="activity_created_idx"),
        ),
    ]
