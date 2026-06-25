from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from clients.models import Case
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES
from clients.views.base import role_required_view


@role_required_view(*ADMIN_PANEL_ALLOWED_ROLES)
def fingerprints_schedule_view(request: HttpRequest) -> HttpResponse:
    """Display upcoming fingerprint appointments per case.

    Fingerprints live on the Case now, so the schedule iterates active cases
    (Case.objects already excludes archived cases, keeping them out of the
    active queue — spec section 10) and joins the client for display.
    """
    today = timezone.localdate()

    upcoming_appointments = list(
        Case.objects.select_related("client")
        .filter(fingerprints_date__isnull=False, fingerprints_date__gte=today)
        .order_by("fingerprints_date", "fingerprints_time")
    )

    past_appointments = list(
        Case.objects.select_related("client")
        .filter(fingerprints_date__isnull=False, fingerprints_date__lt=today)
        .order_by("-fingerprints_date", "-fingerprints_time")[:20]
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
