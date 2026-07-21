"""Client, case-adjacent and staff-facing model admins.

Extracted from the monolithic clients/admin.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import QuerySet
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from clients.constants import DocumentType
from clients.models import (
    AppSettings,
    CaseEmployerAssignment,
    Client,
    ClientActivity,
    Company,
    Document,
    DocumentRequirement,
    EmailLog,
    EmployerChangeCandidate,
    FamilyGroup,
    MOSApplicationData,
    Payment,
    Reminder,
    ServicePrice,
    StaffTask,
)

if TYPE_CHECKING:
    from django.http import HttpRequest


from clients.admin.actions import (
    approve_selected_erasures,
    archive_selected,
    fulfill_erasure_requests,
    place_legal_hold_action,
    release_legal_hold_action,
    restore_selected,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "nip", "regon", "krs", "created_at")
    search_fields = ("name", "nip", "regon", "krs")


@admin.register(EmployerChangeCandidate)
class EmployerChangeCandidateAdmin(admin.ModelAdmin):
    list_display = ("case", "proposed_name", "proposed_nip", "effective_from", "status", "source", "detected_at")
    list_filter = ("status", "source")
    search_fields = ("proposed_name", "proposed_nip", "case__client__first_name", "case__client__last_name")
    readonly_fields = ("fingerprint", "detected_at", "reviewed_at")


@admin.register(CaseEmployerAssignment)
class CaseEmployerAssignmentAdmin(admin.ModelAdmin):
    list_display = ("case", "company", "effective_from", "started_at", "ended_at", "source")
    list_filter = ("source",)


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
    list_filter = ("company", "status", "application_purpose", "family_role", "language", "is_test_data", "archived_at", "erasure_status", "legal_hold", "erasure_requested_at")
    # first_name/last_name/email/phone are encrypted and cannot be searched with
    # the admin's default icontains; only plaintext columns stay in search_fields
    # and get_search_results adds encrypted-field search via the blind indexes.
    search_fields = ("notes", "company__name")

    def get_search_results(self, request, queryset, search_term):
        result_queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        term = (search_term or "").strip()
        if term:
            encrypted_matches = self.model.objects.filter(self.model.build_search_filter(term))
            result_queryset = (result_queryset | queryset.filter(pk__in=encrypted_matches.values("pk"))).distinct()
        return result_queryset, may_have_duplicates
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
        (
            "RODO",
            {
                "fields": (
                    "erasure_status",
                    "erasure_requested_at",
                    "erasure_approved_at",
                    "erasure_approved_by",
                    "erasure_decision_reason",
                    "erasure_fulfilled_at",
                    "legal_hold",
                    "legal_hold_reason",
                )
            },
        ),
    )
    readonly_fields = (
        "archived_at",
        "erasure_status",
        "erasure_requested_at",
        "erasure_approved_at",
        "erasure_approved_by",
        "erasure_fulfilled_at",
        "new_residence_card_application_summary",
        "new_residence_card_application_summary_masked",
    )
    actions = [
        archive_selected,
        restore_selected,
        approve_selected_erasures,
        fulfill_erasure_requests,
        place_legal_hold_action,
        release_legal_hold_action,
    ]

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
    list_filter = ("task_type", "priority", "status", "due_date")
    search_fields = ("title", "description", "client__first_name", "client__last_name", "assignee__email")
    autocomplete_fields = ("client", "assignee", "created_by", "document", "payment")


@admin.register(ClientActivity)
class ClientActivityAdmin(admin.ModelAdmin):
    list_display = ("created_at", "client", "event_type", "summary", "actor_display")
    list_filter = ("event_type", "created_at")
    search_fields = ("summary", "details", "client__first_name", "client__last_name", "actor__email", "actor_label")
    autocomplete_fields = ("client", "actor", "document", "payment", "task")
    # actor_label is a write-once identity snapshot; keep it read-only.
    readonly_fields = ("created_at", "actor_label")

    @admin.display(description="Actor")
    def actor_display(self, obj: ClientActivity) -> str:
        return obj.actor_display


@admin.register(DocumentRequirement)
class DocumentRequirementAdmin(admin.ModelAdmin):
    list_display = ("application_purpose", "document_type", "custom_name", "is_required", "position")
    list_filter = ("application_purpose", "is_required")
    search_fields = ("document_type", "custom_name")
