from __future__ import annotations

from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.http import HttpRequest


class InternalAccountAdapter(DefaultAccountAdapter):
    """Disable public self-signup for the internal staff system."""

    def is_open_for_signup(self, request: HttpRequest) -> bool:
        return False


class InternalSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Disallow automatic public social-account signup as well."""

    def is_open_for_signup(self, request: HttpRequest, sociallogin: Any) -> bool:
        return False
