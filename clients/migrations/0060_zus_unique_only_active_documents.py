# Generated manually to make ZUS RCA month uniqueness ignore soft-deleted documents.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0059_familygroup_client_family_role_client_sponsor_client_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="document",
            name="unique_zus_rca_period_per_client",
        ),
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(
                fields=("client", "document_type", "zus_period_month"),
                condition=models.Q(
                    ("archived_at__isnull", True),
                    ("document_type", "zus_rca_or_insurance"),
                    ("zus_period_month__isnull", False),
                ),
                name="unique_zus_rca_period_per_client",
            ),
        ),
    ]
