from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from django.views.generic import TemplateView

from clients.models import Client
from clients.services.roles import REPORTS_VIEW_ROLES
from clients.views.base import RoleOrFeatureRequiredMixin


class MetricsDashboardView(RoleOrFeatureRequiredMixin, TemplateView):
    template_name = 'clients/metrics_dashboard.html'
    allowed_roles = list(REPORTS_VIEW_ROLES)
    required_permission_name = "can_view_reports"

    def _parse_date_param(self, name: str, default: date) -> date:
        """Parse a YYYY-MM-DD GET param, returning *default* on failure."""
        raw = self.request.GET.get(name, "")
        if not raw:
            return default
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return default

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()

        # Period filters — default last 30 days, support GET ?start=&end=
        end_date = self._parse_date_param("end", today)
        start_date = self._parse_date_param("start", end_date - timedelta(days=30))

        # Use datetime range instead of created_at__date to avoid index issues
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), datetime.min.time()))

        # 1. Clients created in the period
        period_filter = dict(created_at__gte=start_dt, created_at__lt=end_dt)
        clients_created = Client.objects.filter(**period_filter).count()

        # 2. Of those, who uploaded documents
        clients_with_docs = Client.objects.filter(
            **period_filter,
            documents__isnull=False,
        ).distinct().count()

        # 3. Created payments
        clients_with_payments = Client.objects.filter(
            **period_filter,
            payments__isnull=False,
        ).distinct().count()

        # 4. Paid
        clients_paid = Client.objects.filter(
            **period_filter,
            payments__status='paid',
        ).distinct().count()

        # 5. Decision received
        cases_closed = Client.objects.filter(
            **period_filter,
            decision_date__isnull=False,
        ).distinct().count()

        # 6. Overdue SLA — correct logic
        sla_days = getattr(settings, "DECISION_SLA_DAYS", 180)
        overdue_sla = Client.objects.filter(
            workflow_stage="waiting_decision",
            fingerprints_date__isnull=False,
            fingerprints_date__lt=today - timedelta(days=sla_days),
            decision_date__isnull=True,
        ).count()

        context.update({
            'start_date': start_date,
            'end_date': end_date,
            'sla_days': sla_days,
            'funnel': {
                'clients_created': clients_created,
                'clients_with_docs': clients_with_docs,
                'clients_with_payments': clients_with_payments,
                'clients_paid': clients_paid,
                'cases_closed': cases_closed,
            },
            'overdue_sla': overdue_sla,
        })

        return context
