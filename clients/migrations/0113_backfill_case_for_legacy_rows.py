"""Backfill ``case`` for legacy case-less rows (shim-exit, spec §4).

Case-scoped rows created before the Case-first migration may still carry
``case IS NULL``. Every production write path now passes the case explicitly
and the model-level backstop only resolves a *single active* case, so a
legacy row of a client whose only case is archived would never be adopted at
runtime. This migration adopts such rows once and for all:

- a row is linked to its client's case only when the client has EXACTLY ONE
  case overall (archived included) — anything else stays NULL rather than
  guessing;
- MOSApplicationData is OneToOne to Case: a row is linked only when that
  case has no MOS record yet.
"""

from __future__ import annotations

from django.db import migrations
from django.db.models import Count


def _single_case_ids(case_model):
    """client_id -> case_id for clients with exactly one case (any state).

    Historical models use a plain manager, so archived cases are included:
    a legacy row of a client whose only case is archived is adopted too.
    """
    singles = (
        case_model.objects.values("client_id")
        .annotate(n=Count("id"))
        .filter(n=1)
        .values_list("client_id", flat=True)
    )
    return dict(
        case_model.objects.filter(client_id__in=list(singles)).values_list(
            "client_id", "id"
        )
    )


def backfill(apps, schema_editor):
    mapping = _single_case_ids(apps.get_model("clients", "Case"))
    if not mapping:
        return

    simple_models = [
        "Document",
        "ClientDocumentRequirement",
        "Payment",
        "Reminder",
        "StaffTask",
        "EmailLog",
        "WniosekSubmission",
        "PeselApplication",
        "ClientFamilyMemberMOS",
    ]
    for model_name in simple_models:
        model = apps.get_model("clients", model_name)
        for row in model.objects.filter(
            case__isnull=True, client_id__in=mapping.keys()
        ).only("id", "client_id").iterator():
            model.objects.filter(pk=row.pk, case__isnull=True).update(
                case_id=mapping[row.client_id]
            )

    # Onboarding sessions: only case_link sessions carry a case; the portal
    # scope keeps case NULL by design (DB check constraint).
    session_model = apps.get_model("clients", "ClientOnboardingSession")
    for row in (
        session_model.objects.filter(case__isnull=True, client_id__in=mapping.keys())
        .exclude(scope="client_portal")
        .only("id", "client_id")
        .iterator()
    ):
        session_model.objects.filter(pk=row.pk, case__isnull=True).update(
            case_id=mapping[row.client_id]
        )

    # MOSApplicationData: OneToOne to Case — adopt only unoccupied cases.
    mos_model = apps.get_model("clients", "MOSApplicationData")
    occupied = set(
        mos_model.objects.filter(case__isnull=False).values_list("case_id", flat=True)
    )
    for row in mos_model.objects.filter(
        case__isnull=True, client_id__in=mapping.keys()
    ).only("id", "client_id").iterator():
        case_id = mapping[row.client_id]
        if case_id in occupied:
            continue
        mos_model.objects.filter(pk=row.pk, case__isnull=True).update(case_id=case_id)
        occupied.add(case_id)


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0112_alter_mosapplicationdata_new_residence_card_application_status"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
