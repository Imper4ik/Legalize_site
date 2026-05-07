from __future__ import annotations

from typing import Any, TYPE_CHECKING

from django.contrib import admin
from django.db.models import QuerySet

from .models import (
    AppSettings,
    Client,
    ClientActivity,
    Company,
    Document,
    DocumentProcessingJob,
    EmailCampaign,
    EmailLog,
    FamilyGroup,
    Payment,
    Reminder,
    ServicePrice,
    StaffTask,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.action(description="Archive selected records")
def archive_selected(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    for obj in queryset:
        if hasattr(obj, "archive"):
            obj.archive()


@admin.action(description="Restore selected archived records")
def restore_selected(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    base_queryset = getattr(modeladmin.model, "all_objects", None)
    if base_queryset is None:
        return
    for obj in base_queryset.filter(pk__in=queryset.values_list("pk", flat=True)):
        if hasattr(obj, "restore"):
            obj.restore()


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Общие настройки базы",
            {
                "fields": (
                    "organization_name",
                    "contact_email",
                    "contact_phone",
                    "office_address",
                    "default_proxy_name",
                ),
            },
        ),
        (
            "Mazowiecki Wniosek",
            {
                "fields": ("mazowiecki_office_template", "mazowiecki_proxy_template"),
                "description": "Эти значения используются по умолчанию для всей текущей базы данных.",
            },
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ("get_service_code_display", "service_code", "price")
    list_editable = ("price",)
    search_fields = ("service_code",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ("created_at", "updated_at", "archived_at")
    fields = (
        "service_description",
        "total_amount",
        "amount_paid",
        "status",
        "payment_date",
        "payment_method",
        "transaction_id",
        "archived_at",
        "created_at",
        "updated_at",
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("client", "service_description", "total_amount", "status", "due_date", "archived_at", "created_at")
    list_filter = ("status", "service_description", "due_date", "archived_at")
    search_fields = ("client__first_name", "client__last_name", "transaction_id")
    actions = [archive_selected, restore_selected]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Payment]:
        return Payment.all_objects.select_related("client")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    inlines = [PaymentInline]
    list_display = (
        "first_name",
        "last_name",
        "company",
        "case_number",
        "application_purpose",
        "family_role",
        "status",
        "workflow_stage",
        "phone",
        "email",
        "archived_at",
        "created_at",
    )
    list_filter = ("company", "status", "workflow_stage", "application_purpose", "family_role", "language", "archived_at")
    search_fields = ("first_name", "last_name", "email", "phone", "notes", "company__name")
    fieldsets = (
        (
            "Основная информация",
            {"fields": ("first_name", "last_name", "company", "birth_date", "email", "phone", "citizenship", "passport_num")},
        ),
        (
            "Детали подачи",
            {"fields": ("application_purpose", "basis_of_stay", "language", "legal_basis_end_date", "workflow_stage")},
        ),
        ("Семья", {"fields": ("family_role", "sponsor_client")}),
        ("Статус и заметки", {"fields": ("status", "notes", "archived_at")}),
    )
    readonly_fields = ("archived_at",)
    actions = [archive_selected, restore_selected]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Client]:
        return Client.all_objects.select_related("company")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "client",
        "document_type",
        "verified",
        "awaiting_confirmation",
        "ocr_status",
        "zus_period_month",
        "uploaded_at",
        "archived_at",
    )
    list_filter = (
        "document_type",
        "verified",
        "awaiting_confirmation",
        "ocr_status",
        "zus_period_month",
        "archived_at",
    )
    search_fields = ("client__first_name", "client__last_name")
    readonly_fields = ("archived_at",)
    actions = [archive_selected, restore_selected]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Document]:
        return Document.all_objects.select_related("client")


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "reminder_type", "due_date", "is_active", "created_at")
    list_filter = ("reminder_type", "is_active", "due_date")
    search_fields = ("title", "notes", "client__first_name", "client__last_name", "client__email")
    autocomplete_fields = ("client", "payment", "document")
    readonly_fields = ("created_at",)


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ("sent_at", "client", "template_type", "delivery_status", "subject", "sent_by")
    list_filter = ("delivery_status", "template_type", "sent_at")
    search_fields = ("subject", "client__first_name", "client__last_name", "client__email", "sent_by__email")
    autocomplete_fields = ("client", "sent_by")
    readonly_fields = (
        "client",
        "subject",
        "body",
        "recipients",
        "template_type",
        "sent_at",
        "delivery_status",
        "idempotency_key",
        "error_message",
        "sent_by",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


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

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(FamilyGroup)
class FamilyGroupAdmin(admin.ModelAdmin):
    list_display = (
        "sponsor",
        "sponsor_monthly_income",
        "monthly_support_per_person",
        "monthly_housing_cost",
        "meldunek_free_housing",
    )
    search_fields = ("sponsor__first_name", "sponsor__last_name", "sponsor__email")
    autocomplete_fields = ("sponsor",)


@admin.register(StaffTask)
class StaffTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "client", "assignee", "priority", "status", "due_date", "created_at")
    list_filter = ("priority", "status", "due_date")
    search_fields = ("title", "description", "client__first_name", "client__last_name", "assignee__email")
    autocomplete_fields = ("client", "assignee", "created_by", "document", "payment")


@admin.register(ClientActivity)
class ClientActivityAdmin(admin.ModelAdmin):
    list_display = ("created_at", "client", "event_type", "summary", "actor")
    list_filter = ("event_type", "created_at")
    search_fields = ("summary", "details", "client__first_name", "client__last_name", "actor__email")
    autocomplete_fields = ("client", "actor", "document", "payment", "task")
    readonly_fields = ("created_at",)
