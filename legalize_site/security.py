from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.translation import gettext as _


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int
    methods: tuple[str, ...] = ("POST",)
    by_user: bool = True
    by_ip: bool = True
    message: str = _("Too many requests. Please try again later.")


def _client_ip(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "unknown"


def _build_rate_limit_key(request, url_name: str, rule: RateLimitRule) -> str:
    parts: list[str] = ["rl", url_name]
    user = getattr(request, "user", None)
    if rule.by_ip:
        parts.append(f"ip:{_client_ip(request)}")
    if rule.by_user and getattr(user, "is_authenticated", False):
        parts.append(f"user:{user.pk}")
    elif rule.by_user:
        parts.append("user:anon")
    return "|".join(parts)


def is_rate_limited(request, url_name: str, rule: RateLimitRule) -> bool:
    if request.method.upper() not in rule.methods:
        return False

    cache_key = _build_rate_limit_key(request, url_name, rule)
    current = cache.get(cache_key)
    if current is None:
        cache.set(cache_key, 1, timeout=rule.window_seconds)
        return False
    try:
        current = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=rule.window_seconds)
        return False
    return current > rule.limit


def build_rate_limited_response(request, message: str) -> HttpResponse:
    from clients.services.responses import ResponseHelper

    helper = ResponseHelper(request)
    if helper.expects_json:
        return helper.error(message=message, status=429)
    return HttpResponse(message, status=429)


class RateLimitMiddleware:
    """Apply path-name based rate limits to sensitive endpoints."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)

        url_name = match.url_name
        full_name = match.view_name
        configured_rules: dict[str, dict] = getattr(settings, "RATE_LIMITS", {})
        rule_config = configured_rules.get(full_name) or configured_rules.get(url_name)
        if rule_config:
            rule = RateLimitRule(**rule_config)
            if is_rate_limited(request, full_name or url_name or "unknown", rule):
                response = build_rate_limited_response(request, rule.message)
                retry_after = str(rule.window_seconds)
                response["Retry-After"] = retry_after
                response["X-RateLimit-Limit"] = str(rule.limit)
                response["X-RateLimit-Reset"] = str(
                    int(timezone.now().timestamp()) + rule.window_seconds
                )
                return response

        return self.get_response(request)
