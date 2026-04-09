from __future__ import annotations

from allauth.account.internal.flows.email_verification import (
    send_verification_email_to_address,
)
from allauth.account.internal.flows.manage_email import sync_user_email_address
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import ResendVerificationEmailForm


class ResendVerificationEmailView(FormView):
    form_class = ResendVerificationEmailForm
    template_name = "account/resend_verification.html"
    success_url = reverse_lazy("account_email_verification_sent")

    def get_initial(self):
        initial = super().get_initial()
        email = self.request.GET.get("email", "").strip()
        if email:
            initial["email"] = email
        return initial

    def form_valid(self, form):
        email = get_user_model().objects.normalize_email(form.cleaned_data["email"])
        email_address = (
            EmailAddress.objects.select_related("user")
            .filter(email__iexact=email)
            .order_by("-primary", "-verified")
            .first()
        )

        if email_address is None:
            user = get_user_model().objects.filter(email__iexact=email).first()
            if user is not None:
                email_address = sync_user_email_address(user)

        if email_address is not None and not email_address.verified:
            send_verification_email_to_address(self.request, email_address, signup=True)

        return super().form_valid(form)
