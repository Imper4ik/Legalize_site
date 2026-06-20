from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from clients.services.workday import build_workday_context
from clients.views.base import StaffRequiredMixin


class WorkdayView(StaffRequiredMixin, View):
    template_name = "clients/workday.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        context = build_workday_context(request.user)
        return render(request, self.template_name, context)