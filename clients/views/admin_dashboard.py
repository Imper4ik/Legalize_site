from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from clients.models import Client
from clients.services.access import accessible_clients_queryset
from clients.services.roles import REPORTS_VIEW_ROLES
from clients.views.base import RoleRequiredMixin, StaffRequiredMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class AdminDashboardView(RoleRequiredMixin, StaffRequiredMixin, View):
    allowed_roles = list(REPORTS_VIEW_ROLES)
    template_name = "clients/admin_dashboard.html"

    def get_queryset(self) -> QuerySet[Client]:
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if find_spec("pytesseract") is None:
            logger.warning("pytesseract not installed, OCR features will be limited")

        clients = self.get_queryset()
        context = {
            "total_clients": clients.count(),
            "active_clients": clients.count(),
            "pending_documents": clients.filter(documents__ocr_status="pending").distinct().count(),
        }
        return render(request, self.template_name, context)
