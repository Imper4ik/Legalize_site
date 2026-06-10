from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class TestRun(models.Model):
    MODE_SMOKE = "smoke"
    MODE_FULL = "full"
    MODE_OCR = "ocr"
    MODE_EMAIL = "email"
    MODE_ZUS = "zus"
    MODE_DOCUMENTS = "documents"
    MODE_PERMISSIONS = "permissions"
    MODE_SECURITY = "security"
    MODE_WORKFLOW = "workflow"

    MODE_CHOICES = [
        (MODE_SMOKE, "Smoke"),
        (MODE_FULL, "Full"),
        (MODE_OCR, "OCR"),
        (MODE_EMAIL, "Email reminders"),
        (MODE_ZUS, "ZUS RCA"),
        (MODE_DOCUMENTS, "Document access"),
        (MODE_PERMISSIONS, "Permissions"),
        (MODE_SECURITY, "Security"),
        (MODE_WORKFLOW, "Workflow"),
    ]

    STATUS_RUNNING = "running"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_PARTIAL = "partial"

    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_PASSED, "Passed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_PARTIAL, "Partial"),
    ]

    mode = models.CharField(max_length=32, choices=MODE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="started_test_runs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    total_checks = models.PositiveIntegerField(default=0)
    passed_checks = models.PositiveIntegerField(default=0)
    failed_checks = models.PositiveIntegerField(default=0)
    skipped_checks = models.PositiveIntegerField(default=0)
    report_json: models.JSONField[dict[str, Any]] = models.JSONField(default=dict, blank=True)
    is_test_data = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["mode", "-started_at"], name="testrun_mode_started_idx"),
            models.Index(fields=["status", "-started_at"], name="testrun_status_start_idx"),
        ]
        verbose_name = "Test run"
        verbose_name_plural = "Test runs"

    def __str__(self) -> str:
        return f"TestRun #{self.pk} ({self.mode}, {self.status})"

    def refresh_counters(self) -> None:
        results = list(self.results.values_list("status", flat=True))
        self.total_checks = len(results)
        self.passed_checks = sum(1 for status in results if status == TestScenarioResult.STATUS_PASSED)
        self.failed_checks = sum(1 for status in results if status == TestScenarioResult.STATUS_FAILED)
        self.skipped_checks = sum(1 for status in results if status == TestScenarioResult.STATUS_SKIPPED)

    def finish(self) -> None:
        self.refresh_counters()
        if self.failed_checks:
            self.status = self.STATUS_FAILED
        elif self.skipped_checks:
            self.status = self.STATUS_PARTIAL
        else:
            self.status = self.STATUS_PASSED
        self.finished_at = timezone.now()
        self.report_json = {
            **(self.report_json or {}),
            "mode": self.mode,
            "status": self.status,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "skipped_checks": self.skipped_checks,
            "failed": [
                {
                    "scenario_name": result.scenario_name,
                    "expected_result": result.expected_result,
                    "actual_result": result.actual_result,
                    "error_message": result.error_message,
                    "related_client": result.related_client_id,
                    "related_case": result.related_case_identifier,
                    "related_document": result.related_document_id,
                    "created_at": result.created_at.isoformat(),
                }
                for result in self.results.filter(status=TestScenarioResult.STATUS_FAILED).order_by("created_at")
            ],
        }
        self.save(
            update_fields=[
                "status",
                "finished_at",
                "total_checks",
                "passed_checks",
                "failed_checks",
                "skipped_checks",
                "report_json",
            ]
        )


class TestScenarioResult(models.Model):
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PASSED, "Passed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name="results")
    scenario_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    expected_result = models.TextField(blank=True, default="")
    actual_result = models.TextField(blank=True, default="")
    error_message = models.TextField(blank=True, default="")
    related_client = models.ForeignKey(
        "clients.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="test_scenario_results",
    )
    related_case_identifier = models.CharField(max_length=255, blank=True, default="")
    related_document = models.ForeignKey(
        "clients.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="test_scenario_results",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_test_data = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["test_run", "status"], name="testresult_run_status_idx"),
            models.Index(fields=["scenario_name"], name="testresult_scenario_idx"),
        ]
        verbose_name = "Test scenario result"
        verbose_name_plural = "Test scenario results"

    def __str__(self) -> str:
        return f"{self.scenario_name}: {self.status}"
