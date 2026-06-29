from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from clients.constants import DocumentType

from .models import (
    AppSettings,
    Client,
    ClientActivity,
    ClientDigitalAccess,
    ClientFamilyMemberMOS,
    ClientOnboardingSession,
    Company,
    Document,
    DocumentProcessingJob,
    DocumentRequirement,
    EmailCampaign,
    EmailLog,
    FamilyGroup,
    MOSApplicationData,
    Payment,
    PeselApplication,
    Reminder,
    ServicePrice,
    StaffAuditEvent,
    StaffTask,
    TestRun,
    TestScenarioResult,
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
    list_filter = ("status", "service_description", "due_date", "is_test_data", "archived_at")
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
        "application_purpose",
        "family_role",
        "status",
        "phone",
        "email",
        "archived_at",
        "created_at",
    )
    list_filter = ("company", "status", "application_purpose", "family_role", "language", "is_test_data", "archived_at")
    search_fields = ("first_name", "last_name", "email", "phone", "notes", "company__name")
    fieldsets = (
        (
            "Основная информация",
            {"fields": ("first_name", "last_name", "company", "birth_date", "email", "phone", "citizenship", "passport_num")},
        ),
        (
            "Детали подачи",
            {"fields": ("application_purpose", "basis_of_stay", "language", "legal_basis_end_date")},
        ),
        (
            "Nowy wniosek o kartę pobytu / Новое заявление на карту побыту",
            {"fields": ("new_residence_card_application_summary",)},
        ),
        ("Семья", {"fields": ("family_role", "sponsor_client")}),
        ("Статус и заметки", {"fields": ("status", "notes", "archived_at")}),
    )
    readonly_fields = (
        "archived_at",
        "new_residence_card_application_summary",
        "new_residence_card_application_summary_masked",
    )
    actions = [archive_selected, restore_selected]

    def passport_num_masked(self, obj):
        from clients.security.encrypted import safe_encrypted_attr
        val = safe_encrypted_attr(obj, "passport_num")
        if not val:
            return "-"
        return val[:2] + "*" * (len(val) - 4) + val[-2:] if len(val) > 4 else "***"
    passport_num_masked.short_description = "Номер паспорта (Masked)"

    def phone_masked(self, obj):
        if not obj.phone:
            return "-"
        val = str(obj.phone)
        return val[:3] + "*" * (len(val) - 6) + val[-2:] if len(val) > 5 else "***"
    phone_masked.short_description = "Телефон (Masked)"

    def email_masked(self, obj):
        if not obj.email:
            return "-"
        val = str(obj.email)
        if "@" in val:
            parts = val.split("@")
            name, domain = parts[0], parts[1]
            return name[:1] + "***@" + domain
        return "***"
    email_masked.short_description = "Email (Masked)"

    def _mask_case_number_value(self, value):
        if not value:
            return "-"
        val = str(value)
        if "-" in val:
            parts = val.split("-")
            return parts[0] + "-***-" + parts[-1]
        return val[:3] + "***" + val[-4:] if len(val) > 7 else "***"

    def _new_residence_card_application_summary(self, obj, *, masked: bool):
        mos_data = getattr(obj, "mos_application_data", None)
        if not mos_data or not mos_data.new_residence_card_application_status:
            return "-"

        status = mos_data.get_new_residence_card_application_status_display()
        rows = [("Status:", status)]
        if mos_data.new_residence_card_application_status == MOSApplicationData.NEW_CARD_STATUS_YES:
            case_number = mos_data.new_residence_card_case_number or ""
            rows.append(("Numer sprawy / Номер дела:", self._mask_case_number_value(case_number) if masked else (case_number or "-")))
            rows.append((
                "Data złożenia / Дата подачи:",
                mos_data.new_residence_card_submitted_at.strftime("%Y-%m-%d") if mos_data.new_residence_card_submitted_at else "-",
            ))

        confirmation = (
            obj.documents.filter(document_type=DocumentType.NEW_RESIDENCE_CARD_APPLICATION_CONFIRMATION.value)
            .order_by("-uploaded_at", "-id")
            .first()
        )
        if confirmation:
            if masked:
                rows.append(("Potwierdzenie / Подтверждение:", "Uploaded"))
            else:
                rows.append((
                    "Potwierdzenie / Подтверждение:",
                    format_html(
                        '<a href="{}">{}</a>',
                        reverse("admin:clients_document_change", args=[confirmation.pk]),
                        confirmation.display_name,
                    ),
                ))
        else:
            rows.append(("Potwierdzenie / Подтверждение:", "-"))

        if mos_data.new_residence_card_comment:
            rows.append(("Komentarz / Комментарий:", "[Protected]" if masked else mos_data.new_residence_card_comment))
        rows.append((
            "Ostatnia aktualizacja / Последнее обновление:",
            mos_data.new_residence_card_updated_at.strftime("%Y-%m-%d %H:%M") if mos_data.new_residence_card_updated_at else "-",
        ))
        return format_html_join("", "<div><strong>{}</strong> {}</div>", rows)

    def new_residence_card_application_summary(self, obj):
        return self._new_residence_card_application_summary(obj, masked=False)
    new_residence_card_application_summary.short_description = "Nowy wniosek o kartę pobytu"

    def new_residence_card_application_summary_masked(self, obj):
        return self._new_residence_card_application_summary(obj, masked=True)
    new_residence_card_application_summary_masked.short_description = "Nowy wniosek o kartę pobytu (Masked)"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for f in ["passport_num_masked", "phone_masked", "email_masked"]:
                if f not in readonly:
                    readonly.append(f)
        return readonly

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_list_display = []
            for f in list_display:
                if f in ["passport_num", "phone", "email"]:
                    new_list_display.append(f"{f}_masked")
                else:
                    new_list_display.append(f)
            return new_list_display
        return list_display

    def get_search_fields(self, request):
        # email/phone are masked for users without view_sensitive_data; keeping
        # them searchable would let such users confirm a value by probing for a
        # hit (an oracle). Drop them from search unless the permission is held.
        fields = list(super().get_search_fields(request))
        if not request.user.has_perm("clients.view_sensitive_data"):
            fields = [f for f in fields if f not in ("email", "phone")]
        return fields

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_fieldsets = []
            for label, opts in fieldsets:
                fields = list(opts.get("fields", []))
                new_fields = []
                for f in fields:
                    if f in ["passport_num", "phone", "email"]:
                        new_fields.append(f"{f}_masked")
                    elif f == "new_residence_card_application_summary":
                        new_fields.append("new_residence_card_application_summary_masked")
                    else:
                        new_fields.append(f)
                new_opts = dict(opts)
                new_opts["fields"] = new_fields
                new_fieldsets.append((label, new_opts))
            return new_fieldsets
        return fieldsets

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if object_id and request.user.has_perm("clients.view_sensitive_data"):
            client = self.get_object(request, object_id)
            if client:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=client,
                    actor=request.user,
                    event_type="client_viewed",
                    summary="Просмотр конфиденциальных данных клиента",
                    details=""
                )
        return response

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
        "is_test_data",
        "archived_at",
    )
    list_filter = (
        "document_type",
        "verified",
        "awaiting_confirmation",
        "ocr_status",
        "zus_period_month",
        "is_test_data",
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
    list_filter = ("delivery_status", "template_type", "is_test_data", "sent_at")
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

    def body_masked(self, obj):
        return "*** MASKED ***"
    body_masked.short_description = "Текст письма"

    def recipients_masked(self, obj):
        return "*** MASKED ***"
    recipients_masked.short_description = "Получатели"

    def error_message_masked(self, obj):
        return "*** MASKED ***" if obj.error_message else ""
    error_message_masked.short_description = "Ошибка доставки"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for f in ["body", "recipients", "error_message"]:
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
                if f in ["body", "recipients", "error_message"]:
                    new_fields.append(f"{f}_masked")
                else:
                    new_fields.append(f)
            return new_fields
        return fields

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if object_id and request.user.has_perm("clients.view_sensitive_data"):
            log_obj = self.get_object(request, object_id)
            if log_obj and log_obj.client:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=log_obj.client,
                    actor=request.user,
                    event_type="client_viewed",
                    summary="Просмотр конфиденциального журнала писем",
                    details=""
                )
        return response

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


@admin.register(StaffAuditEvent)
class StaffAuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "target", "actor", "summary")
    list_filter = ("event_type", "created_at")
    search_fields = ("summary", "target__email", "actor__email")
    autocomplete_fields = ("target", "actor")
    readonly_fields = ("created_at",)


@admin.register(ClientOnboardingSession)
class ClientOnboardingSessionAdmin(admin.ModelAdmin):
    list_display = ("client", "status", "expires_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("client__first_name", "client__last_name", "client__email")
    autocomplete_fields = ("client", "payment")


def mask_json_pii(data, keys_to_mask):
    if not isinstance(data, dict):
        return data
    masked = dict(data)
    for k in keys_to_mask:
        if k in masked and masked[k]:
            val = str(masked[k])
            if len(val) > 4:
                masked[k] = val[:2] + "*" * (len(val) - 4) + val[-2:]
            else:
                masked[k] = "***"
    return masked

@admin.register(ClientDigitalAccess)
class ClientDigitalAccessAdmin(admin.ModelAdmin):
    list_display = ("client", "has_pesel", "pesel_verified", "has_trusted_profile", "has_mos_account")
    search_fields = ("client__first_name", "client__last_name")
    autocomplete_fields = ("client",)

    def pesel_masked(self, obj):
        from clients.security.encrypted import safe_encrypted_attr
        val = safe_encrypted_attr(obj, "pesel")
        if not val:
            return "-"
        return val[:2] + "*" * (len(val) - 4) + val[-2:] if len(val) > 4 else "***"
    pesel_masked.short_description = "PESEL"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            if "pesel_masked" not in readonly:
                readonly.append("pesel_masked")
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_fields = []
            for f in fields:
                if f == "pesel":
                    new_fields.append("pesel_masked")
                else:
                    new_fields.append(f)
            return new_fields
        return fields

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if object_id and request.user.has_perm("clients.view_sensitive_data"):
            access = self.get_object(request, object_id)
            if access and access.client:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=access.client,
                    actor=request.user,
                    event_type="client_viewed",
                    summary="Просмотр конфиденциальных данных цифрового доступа",
                    details=""
                )
        return response


@admin.register(MOSApplicationData)
class MOSApplicationDataAdmin(admin.ModelAdmin):
    list_display = ("client", "status", "mos_purpose", "legal_stay_until", "new_residence_card_application_status", "created_at")
    list_filter = ("status", "mos_purpose", "new_residence_card_application_status")
    search_fields = ("client__first_name", "client__last_name")
    autocomplete_fields = ("client", "staff_reviewed_by")

    def _render_json_masked(self, data, mask_keys=None):
        import json

        if not data:
            return "-"
        if mask_keys:
            data = mask_json_pii(data, mask_keys)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return format_html("<pre>{}</pre>", formatted)

    def personal_data_masked(self, obj):
        return self._render_json_masked(obj.personal_data, ["first_name", "last_name", "phone", "email", "birth_date"])
    personal_data_masked.short_description = "Personal data (Masked)"

    def passport_data_masked(self, obj):
        return self._render_json_masked(obj.passport_data, ["document_number"])
    passport_data_masked.short_description = "Passport data (Masked)"

    def address_data_masked(self, obj):
        return self._render_json_masked(obj.address_data, ["street", "house_number", "apartment_number", "home_street", "home_city"])
    address_data_masked.short_description = "Address data (Masked)"

    def stay_data_masked(self, obj):
        return self._render_json_masked(obj.stay_data)
    stay_data_masked.short_description = "Stay data"

    def previous_stays_masked(self, obj):
        return self._render_json_masked(obj.previous_stays)
    previous_stays_masked.short_description = "Previous stays"

    def travel_history_masked(self, obj):
        return self._render_json_masked(obj.travel_history)
    travel_history_masked.short_description = "Travel history"

    def insurance_data_masked(self, obj):
        return self._render_json_masked(obj.insurance_data)
    insurance_data_masked.short_description = "Insurance data"

    def financial_data_masked(self, obj):
        return self._render_json_masked(obj.financial_data)
    financial_data_masked.short_description = "Financial data"

    def legal_declarations_masked(self, obj):
        return self._render_json_masked(obj.legal_declarations)
    legal_declarations_masked.short_description = "Legal declarations"

    def new_residence_card_case_number_masked(self, obj):
        value = obj.new_residence_card_case_number
        if not value:
            return "-"
        value = str(value)
        if "-" in value:
            parts = value.split("-")
            return parts[0] + "-***-" + parts[-1]
        return value[:3] + "***" + value[-4:] if len(value) > 7 else "***"
    new_residence_card_case_number_masked.short_description = "New residence card case number (Masked)"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for f in ["personal_data", "passport_data", "address_data", "stay_data", "previous_stays", "travel_history", "insurance_data", "financial_data", "legal_declarations"]:
                masked_f = f"{f}_masked"
                if masked_f not in readonly:
                    readonly.append(masked_f)
            if "new_residence_card_case_number_masked" not in readonly:
                readonly.append("new_residence_card_case_number_masked")
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_fields = []
            seen = set()
            sensitive_json_fields = [
                "personal_data",
                "passport_data",
                "address_data",
                "stay_data",
                "previous_stays",
                "travel_history",
                "insurance_data",
                "financial_data",
                "legal_declarations",
            ]
            for f in fields:
                if f in sensitive_json_fields:
                    field_name = f"{f}_masked"
                elif f == "new_residence_card_case_number":
                    field_name = "new_residence_card_case_number_masked"
                else:
                    field_name = f
                if field_name not in seen:
                    new_fields.append(field_name)
                    seen.add(field_name)
            return new_fields
        return fields

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if object_id and request.user.has_perm("clients.view_sensitive_data"):
            mos_data = self.get_object(request, object_id)
            if mos_data and mos_data.client:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=mos_data.client,
                    actor=request.user,
                    event_type="client_viewed",
                    summary="Просмотр конфиденциальных данных заявления MOS",
                    details=""
                )
        return response


@admin.register(PeselApplication)
class PeselApplicationAdmin(admin.ModelAdmin):
    list_display = ("client", "status", "staff_checked_at", "created_at")
    list_filter = ("status",)
    search_fields = ("client__first_name", "client__last_name")
    autocomplete_fields = ("client", "staff_checked_by")

    def _render_json_masked(self, data, mask_keys=None):
        import json

        if not data:
            return "-"
        if mask_keys:
            data = mask_json_pii(data, mask_keys)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return format_html("<pre>{}</pre>", formatted)

    def pesel_form_data_masked(self, obj):
        return self._render_json_masked(obj.pesel_form_data, ["first_name", "last_name", "phone", "email", "birth_date", "pesel"])
    pesel_form_data_masked.short_description = "Form data (Masked)"

    def generated_pdf_masked(self, obj):
        return "[Protected]" if obj.generated_pdf else "-"
    generated_pdf_masked.short_description = "Generated PDF"

    def signed_scan_masked(self, obj):
        return "[Protected]" if obj.signed_scan else "-"
    signed_scan_masked.short_description = "Signed Scan"

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for f in ["pesel_form_data_masked", "generated_pdf_masked", "signed_scan_masked"]:
                if f not in readonly:
                    readonly.append(f)
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            new_fields = []
            for f in fields:
                if f in ["pesel_form_data", "generated_pdf", "signed_scan"]:
                    new_fields.append(f"{f}_masked")
                else:
                    new_fields.append(f)
            return new_fields
        return fields

    def change_view(self, request, object_id, form_url="", extra_context=None):
        response = super().change_view(request, object_id, form_url, extra_context)
        if object_id and request.user.has_perm("clients.view_sensitive_data"):
            pesel_app = self.get_object(request, object_id)
            if pesel_app and pesel_app.client:
                from clients.services.activity import log_client_activity
                log_client_activity(
                    client=pesel_app.client,
                    actor=request.user,
                    event_type="client_viewed",
                    summary="Просмотр конфиденциального заявления PESEL",
                    details=""
                )
        return response


@admin.register(ClientFamilyMemberMOS)
class ClientFamilyMemberMOSAdmin(admin.ModelAdmin):
    list_display = ("client", "full_name", "relationship", "citizenship", "applies_for_temporary_residence")
    search_fields = ("full_name", "client__first_name", "client__last_name")
    autocomplete_fields = ("client",)


@admin.register(DocumentRequirement)
class DocumentRequirementAdmin(admin.ModelAdmin):
    list_display = ("application_purpose", "document_type", "custom_name", "is_required", "position")
    list_filter = ("application_purpose", "is_required")
    search_fields = ("document_type", "custom_name")


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

