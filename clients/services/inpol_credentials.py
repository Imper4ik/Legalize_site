from __future__ import annotations

import os
from dataclasses import dataclass

from django.core.exceptions import ImproperlyConfigured

from clients.models import InpolAccount
from clients.services.inpol import InpolCredentials


@dataclass
class ResolvedInpolConfig:
    credentials: InpolCredentials
    base_url: str
    account: InpolAccount | None


def resolve_inpol_config(
    *,
    email: str | None = None,
    password: str | None = None,
    base_url: str | None = None,
) -> ResolvedInpolConfig:
    """Resolve credentials and base URL from parameters, env, or active account."""

    email = email or os.environ.get("INPOL_EMAIL")
    password = password or os.environ.get("INPOL_PASSWORD")
    base_url = base_url or os.environ.get("INPOL_BASE_URL")

    account = None
    if not (email and password and base_url):
        account = (
            InpolAccount.objects.filter(is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
        if account:
            email = email or account.email
            password = password or account.password
            base_url = base_url or account.base_url

    if not email or not password or not base_url:
        raise ImproperlyConfigured(
            "Не хватает данных для доступа к inPOL. Заполните активную учётку или "
            "установите переменные окружения INPOL_EMAIL, INPOL_PASSWORD и INPOL_BASE_URL."
        )

    credentials = InpolCredentials(email=email, password=password)
    return ResolvedInpolConfig(credentials=credentials, base_url=base_url, account=account)
