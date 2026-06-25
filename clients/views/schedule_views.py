from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from clients.models import Case
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES
from clients.views.base import role_required_view


@role_required_view(*ADMIN_PANEL_ALLOWED_ROLES)
def fingerprints_schedule_view(request: HttpRequest) -> HttpResponse:
    """Display upcoming fingerprint appointments across all active cases.

    Fingerprints are process data and live on the Case, so the schedule is
    built from active cases (of non-archived clients), not from the Client.
    """
    today = timezone.localdate()

    base = (
        Case.objects.active()
        .filter(client__archived_at__isnull=True, fingerprints_date__isnull=False)
        .select_related("client")
    )

    upcoming_appointments = list(
        base.filter(fingerprints_date__gte=today).order_by("fingerprints_date", "fingerprints_time")
    )
    past_appointments = list(
        base.filter(fingerprints_date__lt=today).order_by("-fingerprints_date", "-fingerprints_time")[:20]
    )

    return render(
        request,
        "clients/fingerprints_schedule.html",
        {
            "upcoming_appointments": upcoming_appointments,
            "past_appointments": past_appointments,
            "today": today,
        },
    )
