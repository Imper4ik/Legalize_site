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

from clients.models import ClientOnboardingSession, StaffAuditEvent, TestRun, TestScenarioResult
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.testing.cleanup import cleanup_test_data
from clients.testing.e2e_runner import available_modes, ensure_test_center_enabled, run_e2e_scenarios, testcenter_lock

ONBOARDING_CASE_PREFIX = "onboarding:"


def _forbidden(message: str | None = None) -> HttpResponseForbidden:
    if message is None:
        message = _("Test Center is not available.")
    return HttpResponseForbidden(message)


def _audit_event(request: HttpRequest, event_type: str, summary: str, metadata: dict[str, Any]) -> None:
    actor = cast("User", request.user)
    StaffAuditEvent.objects.create(
        actor=actor,
        target=actor,
        event_type=event_type,
        summary=summary,
        metadata=metadata,
    )


def _attach_test_portal_urls(results: list[TestScenarioResult]) -> None:
    """Expose raw onboarding URLs only for still-valid Test Center sessions."""
    now = timezone.now()
    for result in results:
        # Dynamic display-only attribute attached for the template.
        result.onboarding_url = ""  # type: ignore[attr-defined]
        if not result.related_case_identifier.startswith(ONBOARDING_CASE_PREFIX):
            continue
        if not result.related_client_id or not result.related_client or not result.related_client.is_test_data:
            continue

        token = result.related_case_identifier.removeprefix(ONBOARDING_CASE_PREFIX).strip()
        if not token:
            continue

        session_exists = (
            ClientOnboardingSession.objects.filter(
                client_id=result.related_client_id,
                token_hash=hash_onboarding_token(token),
                expires_at__gt=now,
            )
            .exclude(status__in=["revoked", "expired"])
            .exists()
        )
        if session_exists:
            result.onboarding_url = reverse("clients:onboarding_start", kwargs={"token": token})  # type: ignore[attr-defined]


@login_required
def testcenter_view(request: HttpRequest) -> HttpResponse:
    try:
        ensure_test_center_enabled(user=request.user)
    except PermissionDenied as exc:
        return _forbidden(str(exc))

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "clean":
            if request.POST.get("confirm_clean") != "yes":
                messages.error(request, _("Confirm cleanup before deleting test data."))
                return redirect("clients:test_center")
            try:
                with testcenter_lock():
                    report = cleanup_test_data(include_test_runs=True)
            except RuntimeError as exc:
                messages.error(request, str(exc))
                return redirect("clients:test_center")
            _audit_event(
                request,
                StaffAuditEvent.EVENT_TEST_CENTER_CLEANUP,
                "Test Center data cleanup executed",
                report.as_dict(),
            )
            messages.success(request, _("Test data cleanup completed."))
            return redirect("clients:test_center")

        mode = request.POST.get("mode", "smoke")
        if mode not in available_modes():
            messages.error(request, _("Unknown Test Center mode: %(mode)s") % {"mode": mode})
            return redirect("clients:test_center")

        keep_data = request.POST.get("keep_data") == "yes"
        test_run = run_e2e_scenarios(mode=mode, started_by=request.user, cleanup=not keep_data)
        _audit_event(
            request,
            StaffAuditEvent.EVENT_TEST_CENTER_RUN,
            f"Test Center run completed: {mode}",
            {
                "test_run_id": test_run.pk,
                "mode": test_run.mode,
                "status": test_run.status,
                "total_checks": test_run.total_checks,
                "failed_checks": test_run.failed_checks,
                "keep_data": keep_data,
            },
        )
        if keep_data:
            messages.success(
                request,
                _("Test Run #%(run_id)s completed (%(status)s). Test data preserved in database. Use links below to inspect.")
                % {"run_id": test_run.pk, "status": test_run.status}
            )
        else:
            messages.success(
                request,
                _("Test Run #%(run_id)s completed with status %(status)s.")
                % {"run_id": test_run.pk, "status": test_run.status}
            )
        return redirect(f"{request.path}?run_id={test_run.pk}")

    selected_run = None
    run_id = request.GET.get("run_id")
    if run_id:
        selected_run = TestRun.objects.filter(pk=run_id, is_test_data=True).first()
    if selected_run is None:
        selected_run = TestRun.objects.filter(is_test_data=True).order_by("-started_at").first()

    selected_results: list[TestScenarioResult] = []
    if selected_run:
        selected_results = list(
            selected_run.results.select_related("related_client", "related_document").order_by("created_at", "id")
        )
        _attach_test_portal_urls(selected_results)

    latest_runs = TestRun.objects.filter(is_test_data=True).order_by("-started_at")[:10]
    return render(
        request,
        "clients/test_center.html",
        {
            "modes": available_modes(),
            "latest_runs": latest_runs,
            "selected_run": selected_run,
            "selected_results": selected_results,
        },
    )
