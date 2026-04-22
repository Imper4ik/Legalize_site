from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from clients.models import Client, Document, EmailCampaign, Payment, Reminder, StaffTask
from clients.services.roles import SETTINGS_ALLOWED_ROLES


PRIVILEGED_INTERNAL_ROLES = tuple(SETTINGS_ALLOWED_ROLES)


def is_internal_staff_user(user) -> bool:
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
    )


def user_has_internal_role(user, *role_names: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if not is_internal_staff_user(user):
        return False
    if not role_names:
        return True
    return user.groups.filter(name__in=role_names).exists()


def can_access_all_clients(user) -> bool:
    return getattr(user, "is_superuser", False) or user_has_internal_role(user, *PRIVILEGED_INTERNAL_ROLES)


def accessible_clients_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or Client.objects.all()
    if not is_internal_staff_user(user):
        return queryset.none()
    if can_access_all_clients(user):
        return queryset
    return queryset.filter(
        Q(assigned_staff=user) | Q(assigned_staff__isnull=True)
    ).distinct()


def accessible_documents_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or Document.objects.select_related("client")
    return queryset.filter(client__in=accessible_clients_queryset(user, Client.objects.all()))


def accessible_payments_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or Payment.objects.select_related("client")
    return queryset.filter(client__in=accessible_clients_queryset(user, Client.objects.all()))


def accessible_reminders_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or Reminder.objects.select_related("client", "payment", "document")
    return queryset.filter(client__in=accessible_clients_queryset(user, Client.objects.all()))


def accessible_tasks_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or StaffTask.objects.select_related("client", "assignee", "created_by")
    if can_access_all_clients(user):
        return queryset
    return queryset.filter(client__in=accessible_clients_queryset(user, Client.objects.all()))


def accessible_campaigns_queryset(user, queryset: QuerySet | None = None) -> QuerySet:
    queryset = queryset or EmailCampaign.objects.select_related("created_by")
    if not is_internal_staff_user(user):
        return queryset.none()
    if can_access_all_clients(user):
        return queryset
    return queryset.filter(created_by=user)
