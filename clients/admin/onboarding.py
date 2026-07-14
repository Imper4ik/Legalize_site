"""Onboarding, intake, MOS and PESEL model admins.

Extracted from the monolithic clients/admin.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.utils.html import format_html

from clients.models import (
    ClientDigitalAccess,
    ClientFamilyMemberMOS,
    ClientIntakeSubmission,
    ClientOnboardingSession,
    MOSApplicationData,
    PeselApplication,
)

if TYPE_CHECKING:
    pass


from clients.admin.actions import (
    mask_json_pii,
)


@admin.register(ClientOnboardingSession)
class ClientOnboardingSessionAdmin(admin.ModelAdmin):
    list_display = ("client", "status", "expires_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("client__first_name", "client__last_name", "client__email")
    autocomplete_fields = ("client", "payment")


@admin.register(ClientIntakeSubmission)
class ClientIntakeSubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "source", "created_client", "created_case", "submitted_at", "converted_at", "created_at")
    list_filter = ("status", "source", "created_at", "submitted_at", "converted_at")
    search_fields = ("created_client__first_name", "created_client__last_name", "created_client__email")
    autocomplete_fields = ("created_client", "created_by", "converted_by")
    readonly_fields = ("email_hash", "phone_hash", "passport_hash", "created_at", "updated_at")

    def personal_data_masked(self, obj):
        return self._render_json_masked(obj.personal_data, ["first_name", "last_name", "phone", "email", "birth_date", "passport_num", "passport_number", "document_number"])
    personal_data_masked.short_description = "Personal data (Masked)"

    def case_data_masked(self, obj):
        return self._render_json_masked(obj.case_data, ["authority_case_number", "case_number"])
    case_data_masked.short_description = "Case data (Masked)"

    def _render_json_masked(self, data, mask_keys=None):
        import json

        if not data:
            return "-"
        if mask_keys:
            data = mask_json_pii(data, mask_keys)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
        return format_html("<pre>{}</pre>", formatted)

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            for field_name in ("personal_data_masked", "case_data_masked"):
                if field_name not in readonly:
                    readonly.append(field_name)
        return readonly

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if not request.user.has_perm("clients.view_sensitive_data"):
            return [
                "personal_data_masked" if field_name == "personal_data" else
                "case_data_masked" if field_name == "case_data" else
                field_name
                for field_name in fields
            ]
        return fields


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
