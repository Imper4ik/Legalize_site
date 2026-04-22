from django.contrib import admin

from .models import AppSettings, Client, ClientActivity, Company, Document, Payment, ServicePrice, StaffTask


@admin.action(description="Archive selected records")
def archive_selected(modeladmin, request, queryset):
    for obj in queryset:
        if hasattr(obj, "archive"):
            obj.archive()


@admin.action(description="Restore selected archived records")
def restore_selected(modeladmin, request, queryset):
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

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
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

    def get_queryset(self, request):
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
        "status",
        "workflow_stage",
        "phone",
        "email",
        "archived_at",
        "created_at",
    )
    list_filter = ("company", "status", "workflow_stage", "application_purpose", "language", "archived_at")
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
        ("Статус и заметки", {"fields": ("status", "notes", "archived_at")}),
    )
    readonly_fields = ("archived_at",)
    actions = [archive_selected, restore_selected]

    def get_queryset(self, request):
        return Client.all_objects.select_related("company")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("client", "document_type", "uploaded_at", "archived_at")
    list_filter = ("document_type", "archived_at")
    search_fields = ("client__first_name", "client__last_name")
    readonly_fields = ("archived_at",)
    actions = [archive_selected, restore_selected]

    def get_queryset(self, request):
        return Document.all_objects.select_related("client")


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
