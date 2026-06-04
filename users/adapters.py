from __future__ import annotations

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpRequest
from django.urls import reverse

from clients.services.roles import user_has_any_role


class InternalAccountAdapter(DefaultAccountAdapter):
    """Disable public self-signup and route users to the right portal."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False

    def get_login_redirect_url(self, request: HttpRequest) -> str:
        user = request.user
        if user_has_any_role(user, "Admin", "Manager", "Staff", "ReadOnly"):
            return reverse("clients:client_list")
        if user_has_any_role(user, "Translator"):
            return reverse("root_dashboard")
        if hasattr(user, "client_profile") and user.client_profile:
            return reverse("clients:onboarding_start", kwargs={"token": "me"})
        return reverse("root_dashboard")


class InternalSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Disallow automatic public social-account signup as well."""

    def is_open_for_signup(self, request: HttpRequest, sociallogin: Any) -> bool:
        return False
