from __future__ import annotations

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.urls import reverse

from clients.services.roles import user_has_any_role


def _get_client_profile(user: Any) -> Any | None:
    try:
        return user.client_profile
    except ObjectDoesNotExist:
        return None


class InternalAccountAdapter(DefaultAccountAdapter):
    """Disable public self-signup and route users to the right portal."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False

    def pre_login(self, request: HttpRequest, user: Any, **kwargs: Any) -> Any:
        client = _get_client_profile(user)
        login_email = str(kwargs.get("email") or user.email or "").strip()
        client_email = str(getattr(client, "email", "") if client else "").strip()

        if client and login_email and (not client_email or login_email.casefold() == client_email.casefold()):
            email_address = EmailAddress.objects.filter(user=user, email__iexact=login_email).first()
            if email_address is None:
                email_address = EmailAddress.objects.create(
                    user=user,
                    email=login_email,
                    primary=True,
                    verified=True,
                )
            changed_fields: list[str] = []
            if not email_address.primary:
                email_address.primary = True
                changed_fields.append("primary")
            if not email_address.verified:
                email_address.verified = True
                changed_fields.append("verified")
            if email_address.email != login_email:
                email_address.email = login_email
                changed_fields.append("email")
            if changed_fields:
                email_address.save(update_fields=changed_fields)
            EmailAddress.objects.filter(user=user).exclude(pk=email_address.pk).update(primary=False)

        return super().pre_login(request, user, **kwargs)

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        user = request.user
        if user_has_any_role(user, "Admin", "Manager", "Staff", "ReadOnly"):
            return reverse("clients:client_list")
        if user_has_any_role(user, "Translator"):
            return reverse("root_dashboard")
        if _get_client_profile(user):
            return reverse("clients:onboarding_start", kwargs={"token": "me"})
        return reverse("root_dashboard")


class InternalSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Disallow automatic public social-account signup as well."""

    def is_open_for_signup(self, request: HttpRequest, sociallogin: Any) -> bool:
        return False
