from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from django.db import transaction
from django.utils.translation import gettext as _

from clients.models import Client, FamilyGroup

logger = logging.getLogger(__name__)

FAMILY_PURPOSE = "family"
FAMILY_ROLE_SPONSOR = "sponsor"
FAMILY_ROLE_SPOUSE = "family_spouse"
FAMILY_ROLE_CHILD = "family_child"
FAMILY_ROLE_SPOUSE_ALIAS = "spouse"
FAMILY_ROLE_CHILD_ALIAS = "child"
FAMILY_MEMBER_ROLES = {FAMILY_ROLE_SPOUSE, FAMILY_ROLE_CHILD}
LEGACY_FAMILY_MEMBER_ROLES = {
    FAMILY_ROLE_SPOUSE_ALIAS: FAMILY_ROLE_SPOUSE,
    FAMILY_ROLE_CHILD_ALIAS: FAMILY_ROLE_CHILD,
    FAMILY_ROLE_SPOUSE: FAMILY_ROLE_SPOUSE,
    FAMILY_ROLE_CHILD: FAMILY_ROLE_CHILD,
}


@dataclass(frozen=True)
class FamilyIncomeResult:
    group: FamilyGroup
    family_size: int
    sponsor_count: int
    spouse_count: int
    child_count: int
    monthly_support_total: Decimal
    housing_cost: Decimal
    required_income: Decimal
    sponsor_income: Decimal | None
    surplus: Decimal | None
    is_sufficient: bool
    risks: tuple[dict[str, str], ...]
    housing_confirmation_required: bool


def family_sponsor_for(client: Client) -> Client:
    visited: set[int] = set()
    current = client
    while current.sponsor_client_id:
        if current.pk in visited:
            logger.warning("Detected sponsor cycle while resolving family sponsor: client_id=%s", client.pk)
            return client
        visited.add(current.pk)
        current = cast(Client, current.sponsor_client)
    return current


def get_family_members(sponsor: Client) -> Any:
    return sponsor.sponsored_family_members.exclude(pk=sponsor.pk).order_by("family_role", "last_name", "first_name")


def get_existing_family_group(sponsor: Client) -> FamilyGroup | None:
    try:
        return cast(FamilyGroup, sponsor.family_group)
    except FamilyGroup.DoesNotExist:
        return None


def ensure_family_group(sponsor: Client) -> FamilyGroup:
    with transaction.atomic():
        if sponsor.family_role != FAMILY_ROLE_SPONSOR:
            sponsor.family_role = FAMILY_ROLE_SPONSOR
            sponsor.save(update_fields=["family_role"])
        group, _created = FamilyGroup.objects.get_or_create(sponsor=sponsor)
    return cast(FamilyGroup, group)


def get_or_create_family_group(sponsor: Client) -> FamilyGroup:
    return ensure_family_group(sponsor)


def create_family_member(
    *,
    sponsor: Client,
    role: str,
    first_name: str,
    last_name: str,
    email: str = "",
    phone: str = "",
    citizenship: str = "",
) -> Client:
    role = LEGACY_FAMILY_MEMBER_ROLES.get(role, role)
    if role not in FAMILY_MEMBER_ROLES:
        raise ValueError("role must be spouse or child")

    ensure_family_group(sponsor)
    return cast(Client, Client.objects.create(
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        citizenship=citizenship or sponsor.citizenship,
        application_purpose="family",
        family_role=role,
        sponsor_client=sponsor,
        language=sponsor.language,
        status=sponsor.status,
    ))


def calculate_family_income(group: FamilyGroup) -> FamilyIncomeResult:
    sponsor = group.sponsor
    members = list(get_family_members(sponsor))
    spouse_count = sum(1 for member in members if member.family_role in {FAMILY_ROLE_SPOUSE, FAMILY_ROLE_SPOUSE_ALIAS})
    child_count = sum(1 for member in members if member.family_role in {FAMILY_ROLE_CHILD, FAMILY_ROLE_CHILD_ALIAS})
    sponsor_count = 1
    family_size = sponsor_count + len(members)

    support_per_person = group.monthly_support_per_person or Decimal("0.00")
    monthly_support_total = support_per_person * Decimal(family_size)
    housing_cost = Decimal("0.00") if group.meldunek_free_housing else (group.monthly_housing_cost or Decimal("0.00"))
    required_income = monthly_support_total + housing_cost
    sponsor_income = group.sponsor_monthly_income
    surplus = None if sponsor_income is None else sponsor_income - required_income
    is_sufficient = sponsor_income is not None and sponsor_income >= required_income

    risks: list[dict[str, str]] = []
    if sponsor_income is None:
        risks.append(
            {
                "title": _("Недостаточный доход спонсора"),
                "message": _("Доход спонсора не указан."),
            }
        )
    elif sponsor_income < required_income:
        risks.append(
            {
                "title": _("Недостаточный доход спонсора"),
                "message": _("Не хватает: %(amount)s zł") % {"amount": abs(surplus or Decimal("0.00"))},
            }
        )

    if risks:
        logger.info(
            "family income risk: sponsor_client_id=%s required_income=%s sponsor_income=%s risks=%s",
            sponsor.pk,
            required_income,
            sponsor_income,
            len(risks),
        )

    return FamilyIncomeResult(
        group=group,
        family_size=family_size,
        sponsor_count=sponsor_count,
        spouse_count=spouse_count,
        child_count=child_count,
        monthly_support_total=monthly_support_total,
        housing_cost=housing_cost,
        required_income=required_income,
        sponsor_income=sponsor_income,
        surplus=surplus,
        is_sufficient=is_sufficient,
        risks=tuple(risks),
        housing_confirmation_required=bool(group.meldunek_free_housing),
    )
