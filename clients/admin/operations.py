"""Background operations admins (OCR jobs, campaigns, test runs).

Extracted from the monolithic clients/admin.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

from clients.models import (
    DocumentProcessingJob,
    EmailCampaign,
    TestRun,
    TestScenarioResult,
)

if TYPE_CHECKING:
    from django.http import HttpRequest




@admin.register(DocumentProcessingJob)
class DocumentProcessingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "job_type",
        "status",
        "attempts",
        "requires_confirmation",
        "created_at",
        "updated_at",
    )
    list_filter = ("job_type", "status", "requires_confirmation", "created_at")
    search_fields = ("document__client__first_name", "document__client__last_name", "document__client__email")
    autocomplete_fields = ("document", "created_by")
    readonly_fields = (
        "document",
        "created_by",
        "job_type",
        "status",
        "source_file_name",
        "attempts",
        "max_attempts",
        "error_message",
        "next_attempt_at",
        "lease_expires_at",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
        "requires_confirmation",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("created_at", "subject", "status", "total_recipients", "sent_count", "failed_count", "created_by")
    list_filter = ("status", "created_at")
    search_fields = ("subject", "created_by__email")
    autocomplete_fields = ("created_by",)
    readonly_fields = (
        "subject",
        "message",
        "recipient_emails",
        "total_recipients",
        "status",
        "sent_count",
        "failed_count",
        "error_details",
        "filters_snapshot",
        "created_by",
        "created_at",
        "started_at",
        "completed_at",
    )

    def message_masked(self, obj):
        return "*** MASKED ***"
    message_masked.short_description = "Текст письма"

    def recipient_emails_masked(self, obj):
        return "*** MASKED ***"
    recipient_emails_masked.short_description = "Получатели"

    def error_details_masked(self, obj):
        return "*** MASKED ***" if obj.error_details else ""
    error_details_masked.short_description = "Детали ошибок"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for f in ["message", "recipient_emails", "error_details"]:
                if f in readonly:
                    readonly.remove(f)
                masked_f = f"{f}_masked"
                if masked_f not in readonly:
                    readonly.append(masked_f)
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_fields = []
            for f in fields:
                if f in ["message", "recipient_emails", "error_details"]:
                    new_fields.append(f"{f}_masked")
                else:
                    new_fields.append(f)
            return new_fields
        return fields

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(TestRun)
class TestRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "mode",
        "status",
        "started_by",
        "started_at",
        "finished_at",
        "total_checks",
        "passed_checks",
        "failed_checks",
        "skipped_checks",
    )
    list_filter = ("mode", "status", "is_test_data", "started_at")
    search_fields = ("id", "started_by__email")
    readonly_fields = (
        "mode",
        "status",
        "started_by",
        "started_at",
        "finished_at",
        "total_checks",
        "passed_checks",
        "failed_checks",
        "skipped_checks",
        "report_json",
        "is_test_data",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(TestScenarioResult)
class TestScenarioResultAdmin(admin.ModelAdmin):
    list_display = ("created_at", "test_run", "scenario_name", "status", "related_client", "related_document")
    list_filter = ("status", "is_test_data", "created_at")
    search_fields = ("scenario_name", "expected_result", "actual_result", "error_message")
    autocomplete_fields = ("test_run", "related_client", "related_document")
    readonly_fields = (
        "test_run",
        "scenario_name",
        "status",
        "expected_result",
        "actual_result",
        "error_message",
        "related_client",
        "related_case_identifier",
        "related_document",
        "created_at",
        "is_test_data",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
