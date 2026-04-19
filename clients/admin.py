# clients/admin.py

from django.contrib import admin

from .models import Client, ClientActivity, Company, Document, Payment, ServicePrice, StaffTask


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ("get_service_code_display", "service_code", "price")
    list_editable = ("price",)
    search_fields = ("service_code",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 1
    readonly_fields = ("created_at", "updated_at")
    fields = (
        "service_description",
        "total_amount",
        "amount_paid",
        "status",
        "payment_date",
        "payment_method",
        "transaction_id",
        "created_at",
        "updated_at",
    )


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("client", "service_description", "total_amount", "status", "due_date", "created_at")
    list_filter = ("status", "service_description", "due_date")
    search_fields = ("client__first_name", "client__last_name", "transaction_id")


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    inlines = [PaymentInline]
    list_display = (
        "first_name",
        "last_name",
        "company",
        "case_number",
        "application_purpose",
        "status",
        "workflow_stage",
        "phone",
        "email",
        "created_at",
    )
    list_filter = ("company", "status", "workflow_stage", "application_purpose", "language")
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
        ("Статус и заметки", {"fields": ("status", "notes")}),
    )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("client", "document_type", "uploaded_at")
    list_filter = ("document_type",)
    search_fields = ("client__first_name", "client__last_name")


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
