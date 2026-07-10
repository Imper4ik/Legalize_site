from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.db.models import QuerySet

from clients.models import Case, Client, Document, EmailCampaign, Payment, Reminder, StaffTask
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

OFFICE_WIDE_ACCESS_ROLES = ("Admin", "Manager", "Staff")
PRIVILEGED_INTERNAL_ROLES = OFFICE_WIDE_ACCESS_ROLES


def _user_group_names(user: AbstractBaseUser | AnonymousUser) -> frozenset[str]:
    """Group names for ``user``, memoized on the user object for the request.

    Role checks run many times per request (navigation, context processors,
    per-view guards). Without this cache each call issues a fresh ``auth_group``
    query, which on list pages showed up as dozens of identical lookups.
    """
    cached = getattr(user, "_cached_group_names", None)
    if cached is not None:
        return cached
    groups = getattr(user, "groups", None)
    names: frozenset[str] = frozenset(groups.values_list("name", flat=True)) if groups is not None else frozenset()
    try:
        user._cached_group_names = names  # type: ignore[union-attr]
    except (AttributeError, TypeError):  # pragma: no cover - exotic user objects
        pass
    return names


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

    return bool(_user_group_names(user) & frozenset(ADMIN_PANEL_ALLOWED_ROLES))


def user_has_internal_role(user: AbstractBaseUser | AnonymousUser | None, *role_names: str) -> bool:
    if user is None:
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not is_internal_staff_user(user):
        return False
    if not role_names:
        return True

    return bool(_user_group_names(user) & frozenset(role_names))


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


def accessible_documents_queryset(
    user: AbstractBaseUser | AnonymousUser | None,
    queryset: QuerySet[Document] | None = None,
    *,
    include_archived_cases: bool = False,
) -> QuerySet[Document]:
    if queryset is None:
        queryset = Document.objects.select_related("client", "case")

    queryset = queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all()),
    )
    if not include_archived_cases:
        queryset = queryset.filter(case__archived_at__isnull=True)
    return queryset


def accessible_payments_queryset(
    user: AbstractBaseUser | AnonymousUser | None,
    queryset: QuerySet[Payment] | None = None,
    *,
    include_archived_cases: bool = False,
) -> QuerySet[Payment]:
    if queryset is None:
        queryset = Payment.objects.select_related("client", "case")

    queryset = queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all()),
    )
    if not include_archived_cases:
        queryset = queryset.filter(case__archived_at__isnull=True)
    return queryset


def accessible_reminders_queryset(
    user: AbstractBaseUser | AnonymousUser | None,
    queryset: QuerySet[Reminder] | None = None,
    *,
    include_archived_cases: bool = False,
) -> QuerySet[Reminder]:
    if queryset is None:
        queryset = Reminder.objects.select_related("client", "case", "payment", "document")

    queryset = queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all()),
    )
    if not include_archived_cases:
        queryset = queryset.filter(case__archived_at__isnull=True)
    return queryset


def accessible_tasks_queryset(
    user: AbstractBaseUser | AnonymousUser | None,
    queryset: QuerySet[StaffTask] | None = None,
    *,
    include_archived_cases: bool = False,
) -> QuerySet[StaffTask]:
    if queryset is None:
        queryset = StaffTask.objects.select_related("client", "assignee", "created_by", "case")

    if not is_internal_staff_user(user):
        return queryset.none()

    queryset = queryset.filter(
        client__in=accessible_clients_queryset(user, Client.objects.all()),
    )
    if not include_archived_cases:
        queryset = queryset.filter(case__archived_at__isnull=True)
    return queryset


def accessible_campaigns_queryset(user: AbstractBaseUser | AnonymousUser | None, queryset: QuerySet[EmailCampaign] | None = None) -> QuerySet[EmailCampaign]:
    if queryset is None:
        queryset = EmailCampaign.objects.select_related("created_by")

    if not is_internal_staff_user(user):
        return queryset.none()

    if can_access_all_clients(user):
        return queryset

    # Cast user to Any for ForeignKey lookup compatibility in filter
    return queryset.filter(created_by=cast(Any, user))
