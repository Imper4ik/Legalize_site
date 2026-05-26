from __future__ import annotations

import hashlib
import hmac
import secrets
from django.conf import settings


def hash_onboarding_token(raw_token: str) -> str:
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, raw_token.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_onboarding_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_onboarding_token(raw)
