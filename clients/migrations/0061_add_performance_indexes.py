"""Add performance indexes for frequent queries.

Indexes added:
- Document.expiry_date (partial: IS NOT NULL)
- EmailLog (client, -sent_at)
- EmailLog (client, template_type)
- ClientActivity (client, -created_at)
- StaffTask (status, due_date)
- StaffTask (client, status, due_date)
- StaffTask (assignee, status, due_date)
- DocumentVersion (document, -version_number)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0060_normalize_legacy_family_purposes"),
    ]

    operations = [
        # Document expiry_date — partial index (only where NOT NULL)
        migrations.AddIndex(
            model_name="document",
            index=models.Index(
                fields=["expiry_date"],
                name="doc_expiry_date_idx",
                condition=models.Q(expiry_date__isnull=False),
            ),
        ),
        # EmailLog (client, -sent_at)
        migrations.AddIndex(
            model_name="emaillog",
            index=models.Index(
                fields=["client", "-sent_at"],
                name="emaillog_client_sent_idx",
            ),
        ),
        # EmailLog (client, template_type)
        migrations.AddIndex(
            model_name="emaillog",
            index=models.Index(
                fields=["client", "template_type"],
                name="emaillog_client_tmpl_idx",
            ),
        ),
        # ClientActivity (client, -created_at)
        migrations.AddIndex(
            model_name="clientactivity",
            index=models.Index(
                fields=["client", "-created_at"],
                name="activity_client_created_idx",
            ),
        ),
        # StaffTask (status, due_date)
        migrations.AddIndex(
            model_name="stafftask",
            index=models.Index(
                fields=["status", "due_date"],
                name="task_status_due_idx",
            ),
        ),
        # StaffTask (client, status, due_date)
        migrations.AddIndex(
            model_name="stafftask",
            index=models.Index(
                fields=["client", "status", "due_date"],
                name="task_client_status_due_idx",
            ),
        ),
        # StaffTask (assignee, status, due_date)
        migrations.AddIndex(
            model_name="stafftask",
            index=models.Index(
                fields=["assignee", "status", "due_date"],
                name="task_assignee_status_due_idx",
            ),
        ),
        # DocumentVersion (document, -version_number)
        migrations.AddIndex(
            model_name="documentversion",
            index=models.Index(
                fields=["document", "-version_number"],
                name="docver_doc_version_idx",
            ),
        ),
    ]
