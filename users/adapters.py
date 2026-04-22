from __future__ import annotations

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class InternalAccountAdapter(DefaultAccountAdapter):
    """Disable public self-signup for the internal staff system."""

    def is_open_for_signup(self, request):
        return False


class InternalSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Disallow automatic public social-account signup as well."""

    def is_open_for_signup(self, request, sociallogin):
        return False
