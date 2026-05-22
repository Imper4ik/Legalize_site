from django.db.models import Q
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

    def get_queryset(self):
        qs = super().get_queryset().select_related("client", "sent_by")
        form = EmailLogFilterForm(self.request.GET)
        
        if form.is_valid():
            status = form.cleaned_data.get("status")
            if status:
                qs = qs.filter(delivery_status=status)
                
            date_start = form.cleaned_data.get("date_start")
            if date_start:
                qs = qs.filter(sent_at__date__gte=date_start)
                
            date_end = form.cleaned_data.get("date_end")
            if date_end:
                qs = qs.filter(sent_at__date__lte=date_end)
                
            search = form.cleaned_data.get("search")
            if search:
                qs = qs.filter(
                    Q(subject__icontains=search) |
                    Q(client__first_name__icontains=search) |
                    Q(client__last_name__icontains=search)
                )
                
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = EmailLogFilterForm(self.request.GET or None)
        return context


class StaffActivityLogsView(BaseLogView):
    model = ClientActivity
    template_name = "clients/logs/staff_activity_logs.html"
    context_object_name = "activities"

    def get_queryset(self):
        qs = super().get_queryset().select_related("actor", "client", "document", "payment")
        form = StaffActivityFilterForm(self.request.GET)
        
        if form.is_valid():
            actor = form.cleaned_data.get("actor")
            if actor:
                qs = qs.filter(actor=actor)
                
            date_start = form.cleaned_data.get("date_start")
            if date_start:
                qs = qs.filter(created_at__date__gte=date_start)
                
            date_end = form.cleaned_data.get("date_end")
            if date_end:
                qs = qs.filter(created_at__date__lte=date_end)
                
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = StaffActivityFilterForm(self.request.GET or None)
        return context
