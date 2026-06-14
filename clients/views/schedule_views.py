from __future__ import annotations

from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from clients.models import Client
from clients.security.encrypted import safe_encrypted_attr
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES
from clients.views.base import role_required_view


@role_required_view(*ADMIN_PANEL_ALLOWED_ROLES)
def fingerprints_schedule_view(request: HttpRequest) -> HttpResponse:
    """View to display upcoming fingerprint appointments for all clients."""
    today = timezone.localdate()

    # Get all clients with fingerprints_date set, ordered by date and time
    # Focus on future and today appointments by default
    upcoming_appointments = list(
        Client.objects.defer("case_number", "passport_num").filter(
            fingerprints_date__isnull=False
        ).filter(
            Q(fingerprints_date__gte=today)
        ).order_by("fingerprints_date", "fingerprints_time")
    )
    for client in upcoming_appointments:
        client.safe_case_number = safe_encrypted_attr(client, "case_number", default="-")

    # Also get some recent past appointments for context
    past_appointments = list(
        Client.objects.defer("case_number", "passport_num").filter(
            fingerprints_date__lt=today
        ).order_by("-fingerprints_date", "-fingerprints_time")[:20]
    )
    for client in past_appointments:
        client.safe_case_number = safe_encrypted_attr(client, "case_number", default="-")

    return render(
        request,
        "clients/fingerprints_schedule.html",
        {
            "upcoming_appointments": upcoming_appointments,
            "past_appointments": past_appointments,
            "today": today,
        },
    )
