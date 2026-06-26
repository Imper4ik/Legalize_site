from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from users.models import User

from clients.demo.demo_cleanup import cleanup_demo_data
from clients.demo.demo_factory import get_demo_token_for_client
from clients.demo.demo_runner import democenter_lock, ensure_demo_center_enabled, prepare_demo
from clients.models import Client, Document, DocumentProcessingJob, EmailLog, StaffAuditEvent
from clients.services.onboarding_tokens import hash_onboarding_token


def _forbidden(message: str | None = None) -> HttpResponseForbidden:
    if message is None:
        message = _("Demo Center is not available.")
    return HttpResponseForbidden(message)


def _audit_event(request: HttpRequest, event_type: str, summary: str, metadata: dict[str, Any]) -> None:
    actor = cast("User", request.user)
    StaffAuditEvent.objects.create(
        actor=actor,
        target=actor,
        event_type=event_type,
        summary=summary,
        metadata=metadata,
        is_demo_data=True,
    )


@login_required
def democenter_view(request: HttpRequest) -> HttpResponse:
    try:
        ensure_demo_center_enabled(user=request.user)
    except PermissionDenied as exc:
        return _forbidden(str(exc))

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "clean":
            if request.POST.get("confirm_clean") != "yes":
                messages.error(request, _("Confirm cleanup before deleting demo data."))
                return redirect("clients:demo_center")
            try:
                with democenter_lock():
                    report = cleanup_demo_data()
            except RuntimeError as exc:
                messages.error(request, str(exc))
                return redirect("clients:demo_center")
            _audit_event(
                request,
                "demo_center_cleanup",
                "Demo Center data cleanup executed",
                report,
            )
            messages.success(request, _("Demo data cleanup completed."))
            return redirect("clients:demo_center")

        elif action == "prepare":
            try:
                results = prepare_demo(request.user)
                _audit_event(
                    request,
                    "demo_center_prepare",
                    "Demo Center scenarios generated successfully",
                    {"clients_created": len(results)},
                )
                messages.success(request, _("5-minute demo environment prepared successfully."))
            except Exception as exc:
                messages.error(request, _("Failed to prepare demo environment: ") + str(exc))
            return redirect("clients:demo_center")

    # GET request
    demo_clients = list(Client.all_objects.filter(is_demo_data=True).order_by("id"))
    demo_clients_by_first_name: dict[str, Client] = {}
    purpose_counts = {value: 0 for value, _label in Client.APPLICATION_PURPOSE_CHOICES}
    stale_portal_links = 0
    for client in demo_clients:
        demo_clients_by_first_name[client.first_name.lower()] = client
        purpose_counts[client.application_purpose] = purpose_counts.get(client.application_purpose, 0) + 1
        token = get_demo_token_for_client(client)
        session = (
            client.onboarding_sessions.filter(
                token_hash=hash_onboarding_token(token),
                expires_at__gt=timezone.now(),
            )
            .exclude(status__in=["revoked", "expired"])
            .first()
        )
        if session:
            # Dynamic display-only attribute attached for the template.
            client.portal_url = request.build_absolute_uri(  # type: ignore[attr-defined]
                reverse("clients:onboarding_start", kwargs={"token": token})
            )
        else:
            client.portal_url = None  # type: ignore[attr-defined]
            if client.onboarding_sessions.exists():
                stale_portal_links += 1

    demo_emails = EmailLog.objects.filter(is_demo_data=True).order_by("-sent_at")[:10]
    demo_jobs = DocumentProcessingJob.objects.filter(is_demo_data=True).order_by("-created_at")[:10]
    demo_ocr_document = (
        Document.all_objects.filter(is_demo_data=True, awaiting_confirmation=True)
        .select_related("client")
        .order_by("-uploaded_at")
        .first()
    )
    demo_purposes = [
        {
            "value": value,
            "label": str(label),
            "count": purpose_counts.get(value, 0),
        }
        for value, label in Client.APPLICATION_PURPOSE_CHOICES
    ]
    demo_needs_refresh = bool(demo_clients) and (not purpose_counts.get("family") or stale_portal_links > 0)

    return render(
        request,
        "clients/demo_center.html",
        {
            "demo_clients": demo_clients,
            "demo_clients_by_first_name": demo_clients_by_first_name,
            "demo_daria": demo_clients_by_first_name.get("daria"),
            "demo_ivan": demo_clients_by_first_name.get("ivan"),
            "demo_emails": demo_emails,
            "demo_jobs": demo_jobs,
            "demo_ocr_document": demo_ocr_document,
            "demo_purposes": demo_purposes,
            "demo_needs_refresh": demo_needs_refresh,
            "stale_portal_links": stale_portal_links,

        },
    )
