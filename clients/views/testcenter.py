from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render

from clients.models import StaffAuditEvent, TestRun
from clients.testing.cleanup import cleanup_test_data
from clients.testing.e2e_runner import available_modes, ensure_test_center_enabled, run_e2e_scenarios, testcenter_lock


def _forbidden(message: str = "Test Center is not available.") -> HttpResponseForbidden:
    return HttpResponseForbidden(message)


def _audit_event(request: HttpRequest, event_type: str, summary: str, metadata: dict[str, Any]) -> None:
    StaffAuditEvent.objects.create(
        actor=request.user,
        target=request.user,
        event_type=event_type,
        summary=summary,
        metadata=metadata,
    )


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
                messages.error(request, "Confirm cleanup before deleting test data.")
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
            messages.success(request, "Test data cleanup completed.")
            return redirect("clients:test_center")

        mode = request.POST.get("mode", "smoke")
        if mode not in available_modes():
            messages.error(request, f"Unknown Test Center mode: {mode}")
            return redirect("clients:test_center")

        test_run = run_e2e_scenarios(mode=mode, started_by=request.user, cleanup=True)
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
            },
        )
        messages.success(request, f"Test Run #{test_run.pk} completed with status {test_run.status}.")
        return redirect(f"{request.path}?run_id={test_run.pk}")

    selected_run = None
    run_id = request.GET.get("run_id")
    if run_id:
        selected_run = TestRun.objects.filter(pk=run_id, is_test_data=True).first()
    if selected_run is None:
        selected_run = TestRun.objects.filter(is_test_data=True).order_by("-started_at").first()

    latest_runs = TestRun.objects.filter(is_test_data=True).order_by("-started_at")[:10]
    return render(
        request,
        "clients/test_center.html",
        {
            "modes": available_modes(),
            "latest_runs": latest_runs,
            "selected_run": selected_run,
        },
    )
