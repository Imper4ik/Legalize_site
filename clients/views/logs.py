from datetime import datetime, time, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone
from django.views.generic import ListView

from clients.forms import EmailLogFilterForm, StaffActivityFilterForm
from clients.models.activity import ClientActivity
from clients.models.email import EmailLog
from clients.views.base import RoleRequiredMixin


class BaseLogView(RoleRequiredMixin, ListView):
    paginate_by = 50
    allowed_roles = ["Admin", "Manager"]


class EmailLogsView(BaseLogView):
    model = EmailLog
    template_name = "clients/logs/email_logs.html"
    context_object_name = "logs"

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("client", "sent_by")
        form = EmailLogFilterForm(self.request.GET)

        if form.is_valid():
            status = form.cleaned_data.get("status")
            if status:
                qs = qs.filter(delivery_status=status)

            date_start = form.cleaned_data.get("date_start")
            if date_start:
                start_dt = timezone.make_aware(datetime.combine(date_start, time.min), timezone.get_current_timezone())
                qs = qs.filter(sent_at__gte=start_dt)

            date_end = form.cleaned_data.get("date_end")
            if date_end:
                end_dt = timezone.make_aware(
                    datetime.combine(date_end + timedelta(days=1), time.min),
                    timezone.get_current_timezone(),
                )
                qs = qs.filter(sent_at__lt=end_dt)

            search = form.cleaned_data.get("search")
            if search:
                from clients.models import Client

                matching_clients = Client.objects.filter(Client.build_search_filter(search))
                qs = qs.filter(
                    Q(subject__icontains=search) |
                    Q(client__in=matching_clients)
                )

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["filter_form"] = EmailLogFilterForm(self.request.GET or None)
        return context


class StaffActivityLogsView(BaseLogView):
    model = ClientActivity
    template_name = "clients/logs/staff_activity_logs.html"
    context_object_name = "activities"

    def get_queryset(self) -> Any:
        qs = super().get_queryset().select_related("actor", "client", "document", "payment")
        form = StaffActivityFilterForm(self.request.GET)

        if form.is_valid():
            actor = form.cleaned_data.get("actor")
            if actor:
                qs = qs.filter(actor=actor)

            date_start = form.cleaned_data.get("date_start")
            if date_start:
                start_dt = timezone.make_aware(datetime.combine(date_start, time.min), timezone.get_current_timezone())
                qs = qs.filter(created_at__gte=start_dt)

            date_end = form.cleaned_data.get("date_end")
            if date_end:
                end_dt = timezone.make_aware(
                    datetime.combine(date_end + timedelta(days=1), time.min),
                    timezone.get_current_timezone(),
                )
                qs = qs.filter(created_at__lt=end_dt)

        return qs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["filter_form"] = StaffActivityFilterForm(self.request.GET or None)
        return context
