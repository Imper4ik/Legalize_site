from __future__ import annotations

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView

from clients.forms import InpolAccountForm
from clients.models import InpolAccount
from clients.views.base import StaffRequiredMixin


class InpolAccountView(StaffRequiredMixin, FormView):
    template_name = "clients/inpol_account_form.html"
    form_class = InpolAccountForm
    success_url = reverse_lazy("clients:inpol_account")

    def get_initial(self):
        initial = super().get_initial()
        latest = InpolAccount.objects.order_by("-updated_at", "-id").first()
        if latest:
            initial.update(
                {
                    "name": latest.name,
                    "base_url": latest.base_url,
                    "email": latest.email,
                    "password": latest.password,
                    "is_active": latest.is_active,
                }
            )
        return initial

    def form_valid(self, form):
        account = form.save()
        if account.is_active:
            messages.success(self.request, "Учётные данные inPOL сохранены и активированы.")
        else:
            messages.success(self.request, "Учётные данные inPOL сохранены.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from os import environ

        poll_interval = environ.get("INPOL_POLL_INTERVAL", "900")
        try:
            interval_seconds = int(poll_interval)
        except ValueError:
            interval_seconds = 900
        context["inpol_poll_interval_minutes"] = max(1, interval_seconds // 60)
        return context
