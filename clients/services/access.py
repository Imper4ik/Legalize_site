from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import QuerySet

from clients.models import Case, Client, Document, EmailCampaign, Payment, Reminder, StaffTask
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

OFFICE_WIDE_ACCESS_ROLES = ("Admin", "Manager", "Staff")
PRIVILEGED_INTERNAL_ROLES = OFFICE_WIDE_ACCESS_ROLES


def is_internal_staff_user(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    if user is None:
        return False
    if not (
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
    ):
        return False
    if getattr(user, "is_superuser", False):
        return True

    # Check groups if it's a real user object
    groups = getattr(user, "groups", None)
    if groups:
        return bool(groups.filter(name__in=ADMIN_PANEL_ALLOWED_ROLES).exists())
    return False


def user_has_internal_role(user: AbstractBaseUser | AnonymousUser | None, *role_names: str) -> bool:
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not is_internal_staff_user(user):
        return False
    if not role_names:
        return True

    groups = getattr(user, "groups", None)
    if groups:
        return bool(groups.filter(name__in=role_names).exists())
    return False


def can_access_all_clients(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    return bool(getattr(user, "is_superuser", False) or user_has_internal_role(
        user,
        *PRIVILEGED_INTERNAL_ROLES,
    ))


def accessible_clients_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[Client] | None = None) -> QuerySet[Client]:
    if queryset is None:
        queryset = Client.objects.all()

    if not is_internal_staff_user(user):
        return queryset.none()

    # There is no per-staff client assignment: every internal staff member has
    # office-wide read access. Mutation is gated separately by role checks
    # (spec §2). ReadOnly users therefore see all clients but cannot change them.
    return queryset


def accessible_cases_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[Case] | None = None) -> QuerySet[Case]:
    if queryset is None:
        queryset = Case.objects.select_related("client")

    if not is_internal_staff_user(user):
        return queryset.none()

    return queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all())
    )

def accessible_documents_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[Document] | None = None) -> QuerySet[Document]:
    if queryset is None:
        queryset = Document.objects.select_related("client")

    return queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all())
    )


def accessible_payments_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[Payment] | None = None) -> QuerySet[Payment]:
    if queryset is None:
        queryset = Payment.objects.select_related("client")

    return queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all())
    )


def accessible_reminders_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[Reminder] | None = None) -> QuerySet[Reminder]:
    if queryset is None:
        queryset = Reminder.objects.select_related("client", "payment", "document")

    return queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all())
    )


def accessible_tasks_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[StaffTask] | None = None) -> QuerySet[StaffTask]:
    if queryset is None:
        queryset = StaffTask.objects.select_related("client", "assignee", "created_by")

    if not is_internal_staff_user(user):
        return queryset.none()

    return queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all())
    )


def accessible_campaigns_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[EmailCampaign] | None = None) -> QuerySet[EmailCampaign]:
    if queryset is None:
        queryset = EmailCampaign.objects.select_related("created_by")

    if not is_internal_staff_user(user):
        return queryset.none()

    if can_access_all_clients(user):
        return queryset

    # Cast user to Any for ForeignKey lookup compatibility in filter
    return queryset.filter(created_by=cast(Any, user))
