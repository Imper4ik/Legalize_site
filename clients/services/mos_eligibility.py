"""MOS 2 online-submission eligibility checks.

MOS 2 (Moduł Obsługi Spraw) accepts most temporary-residence applications
online, but a few categories must still go through a consular/paper route. The
one we can detect from the data we already collect is family reunification when
the foreigner resides outside Poland: such an application cannot be filed in MOS.

This is a non-destructive advisory used to warn staff early, never to block
data entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.utils.translation import gettext_lazy as _

from clients.security.encrypted import read_encrypted_json_dict

# Roles that represent a sponsored family member (not the principal/sponsor).
FAMILY_MEMBER_ROLES = {"family_spouse", "family_child"}


@dataclass(frozen=True)
class MosEligibilityResult:
    """Outcome of an MOS 2 eligibility check.

    ``eligible`` is True unless a hard exclusion was detected. ``reasons`` holds
    human-readable, translatable explanations for any exclusion.
    """

    eligible: bool = True
    reasons: list[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.reasons)


def _resident_outside_poland(mos_data: Any) -> bool:
    """Return True only when the foreigner is explicitly recorded as abroad."""

    if mos_data is None:
        return False
    stay_data, unavailable = read_encrypted_json_dict(mos_data, "stay_data")
    if unavailable:
        return False
    return stay_data.get("is_in_poland") is False


def evaluate_mos_eligibility(client: Any, mos_data: Any | None = None) -> MosEligibilityResult:
    """Evaluate whether a case can be submitted online through MOS 2.

    Args:
        client: the ``Client`` whose application purpose / family role is checked.
        mos_data: optional ``MOSApplicationData``; falls back to the client's
            single MOS record when omitted.
    """

    if mos_data is None:
        mos_data = getattr(client, "mos_application_data", None)
        if mos_data is None:
            related = getattr(client, "mos_applications", None)
            mos_data = related.first() if related is not None else None

    reasons: list[str] = []

    is_family = getattr(client, "application_purpose", "") == "family"
    family_role = getattr(client, "family_role", "") or ""
    if is_family and family_role in FAMILY_MEMBER_ROLES and _resident_outside_poland(mos_data):
        reasons.append(
            str(
                _(
                    "Family reunification cannot be submitted online in MOS while the "
                    "foreigner resides outside Poland — a consular/paper route is required."
                )
            )
        )

    return MosEligibilityResult(eligible=not reasons, reasons=reasons)
