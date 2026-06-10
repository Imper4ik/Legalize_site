from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0084_alter_client_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="is_test_data",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="document",
            name="is_test_data",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="payment",
            name="is_test_data",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="emaillog",
            name="is_test_data",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.CreateModel(
            name="TestRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("smoke", "Smoke"),
                            ("full", "Full"),
                            ("ocr", "OCR"),
                            ("email", "Email reminders"),
                            ("documents", "Document access"),
                            ("permissions", "Permissions"),
                            ("security", "Security"),
                            ("workflow", "Workflow"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("partial", "Partial"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("total_checks", models.PositiveIntegerField(default=0)),
                ("passed_checks", models.PositiveIntegerField(default=0)),
                ("failed_checks", models.PositiveIntegerField(default=0)),
                ("skipped_checks", models.PositiveIntegerField(default=0)),
                ("report_json", models.JSONField(blank=True, default=dict)),
                ("is_test_data", models.BooleanField(db_index=True, default=True)),
                (
                    "started_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="started_test_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Test run",
                "verbose_name_plural": "Test runs",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="TestScenarioResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scenario_name", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("passed", "Passed"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        max_length=20,
                    ),
                ),
                ("expected_result", models.TextField(blank=True, default="")),
                ("actual_result", models.TextField(blank=True, default="")),
                ("error_message", models.TextField(blank=True, default="")),
                ("related_case_identifier", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("is_test_data", models.BooleanField(db_index=True, default=True)),
                (
                    "related_client",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="test_scenario_results",
                        to="clients.client",
                    ),
                ),
                (
                    "related_document",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="test_scenario_results",
                        to="clients.document",
                    ),
                ),
                (
                    "test_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="clients.testrun",
                    ),
                ),
            ],
            options={
                "verbose_name": "Test scenario result",
                "verbose_name_plural": "Test scenario results",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="testrun",
            index=models.Index(fields=["mode", "-started_at"], name="testrun_mode_started_idx"),
        ),
        migrations.AddIndex(
            model_name="testrun",
            index=models.Index(fields=["status", "-started_at"], name="testrun_status_start_idx"),
        ),
        migrations.AddIndex(
            model_name="testscenarioresult",
            index=models.Index(fields=["test_run", "status"], name="testresult_run_status_idx"),
        ),
        migrations.AddIndex(
            model_name="testscenarioresult",
            index=models.Index(fields=["scenario_name"], name="testresult_scenario_idx"),
        ),
        migrations.AlterField(
            model_name="staffauditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("staff_updated", "Staff user updated"),
                    ("staff_active_toggled", "Staff active status toggled"),
                    ("test_center_run", "Test Center run"),
                    ("test_center_cleanup", "Test Center cleanup"),
                ],
                max_length=64,
            ),
        ),
    ]
