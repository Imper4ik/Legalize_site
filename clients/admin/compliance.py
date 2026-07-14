"""RODO/audit model admins (consents, staff audit trail).

Extracted from the monolithic clients/admin.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin

from clients.models import (
    ConsentRecord,
    StaffAuditEvent,
)

if TYPE_CHECKING:
    from django.http import HttpRequest




@admin.register(ConsentRecord)
class ConsentRecordAdmin(admin.ModelAdmin):
    list_display = ("created_at", "client", "purpose", "granted", "channel", "policy_version")
    list_filter = ("purpose", "granted", "channel", "created_at")
    search_fields = ("client__first_name", "client__last_name", "client__email")
    autocomplete_fields = ("client",)
    readonly_fields = (
        "client",
        "case",
        "purpose",
        "granted",
        "policy_version",
        "channel",
        "ip_address",
        "user_agent",
        "created_at",
        "prev_hash",
        "entry_hash",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Consent rows are an append-only audit trail written by the app, not by hand.
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(StaffAuditEvent)
class StaffAuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "target_display", "actor_display", "summary")
    list_filter = ("event_type", "created_at")
    search_fields = ("summary", "target__email", "actor__email", "target_label", "actor_label")
    readonly_fields = (
        "created_at",
        "actor",
        "actor_label",
        "target",
        "target_label",
        "event_type",
        "summary",
        "metadata",
        "is_demo_data",
    )

    @admin.display(description="Target")
    def target_display(self, obj: StaffAuditEvent) -> str:
        return obj.target_display

    @admin.display(description="Actor")
    def actor_display(self, obj: StaffAuditEvent) -> str:
        return obj.actor_display

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
