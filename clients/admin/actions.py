"""Shared admin actions and PII helpers.

Extracted from the monolithic clients/admin.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin
from django.db.models import QuerySet

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


@admin.action(description="Fulfil erasure request (anonymize) — RODO art. 17")
def approve_selected_erasures(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    """Approve reviewed erasure requests (requested → approved), skipping holds."""
    from clients.models import Client
    from clients.services.erasure import ErasureWorkflowError, approve_erasure

    approved = skipped = 0
    for client in queryset:
        if client.erasure_status != Client.ErasureStatus.REQUESTED or client.legal_hold:
            skipped += 1
            continue
        try:
            approve_erasure(client, actor=request.user, reason="Approved via admin review")
            approved += 1
        except ErasureWorkflowError:
            skipped += 1
    modeladmin.message_user(request, f"Approved {approved} erasure(s); skipped {skipped}.")


def fulfill_erasure_requests(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    """Fulfil only APPROVED, non-held requests — never erase on request alone."""
    from clients.models import Client
    from clients.services.anonymization import anonymize_client

    count = skipped = 0
    for client in queryset:
        if client.erasure_status != Client.ErasureStatus.APPROVED or client.legal_hold:
            skipped += 1
            continue
        anonymize_client(client, mark_erasure_fulfilled=True)
        count += 1
    modeladmin.message_user(
        request, f"Anonymized {count} approved client(s); skipped {skipped} (not approved or on hold)."
    )


def place_legal_hold_action(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    from clients.services.erasure import place_legal_hold

    count = 0
    for client in queryset:
        place_legal_hold(client, reason="Placed via admin")
        count += 1
    modeladmin.message_user(request, f"Placed legal hold on {count} client(s).")


def release_legal_hold_action(modeladmin: Any, request: HttpRequest, queryset: QuerySet) -> None:
    from clients.services.erasure import release_legal_hold

    count = 0
    for client in queryset:
        release_legal_hold(client)
        count += 1
    modeladmin.message_user(request, f"Released legal hold on {count} client(s).")


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
