from __future__ import annotations

import logging
from typing import Any, cast, TYPE_CHECKING

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from clients.models import Client
from clients.services.access import accessible_clients_queryset
from clients.services.roles import ADMIN_PANEL_ALLOWED_ROLES
from clients.views.base import RoleRequiredMixin, StaffRequiredMixin

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger(__name__)


class AdminDashboardView(RoleRequiredMixin, StaffRequiredMixin, View):
    allowed_roles = list(ADMIN_PANEL_ALLOWED_ROLES)
    template_name = "clients/admin_dashboard.html"

    def get_queryset(self) -> QuerySet[Client]:
        return accessible_clients_queryset(self.request.user, Client.objects.all())

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            import pytesseract
        except ImportError:
            logger.warning("pytesseract not installed, OCR features will be limited")

        clients = self.get_queryset()
        context = {
            "total_clients": clients.count(),
            "active_clients": clients.active().count(),
            "pending_documents": clients.filter(documents__ocr_status="pending").distinct().count(),
        }
        return render(request, self.template_name, context)
