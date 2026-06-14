from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitRule:
    limit: int
    window_seconds: int
    methods: tuple[str, ...] = ("POST",)
    by_user: bool = True
    by_ip: bool = True
    message: str = _("Too many requests. Please try again later.")


def _client_ip(request: HttpRequest) -> str:
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", "") or "unknown")


def _build_rate_limit_key(request: HttpRequest, url_name: str, rule: RateLimitRule) -> str:
    parts: list[str] = ["rl", url_name]
    user = getattr(request, "user", None)
    if rule.by_ip:
        parts.append(f"ip:{_client_ip(request)}")
    if rule.by_user and getattr(user, "is_authenticated", False):
        parts.append(f"user:{getattr(user, 'pk', 'unknown')}")
    elif rule.by_user:
        parts.append("user:anon")
    return "|".join(parts)


def is_rate_limited(request: HttpRequest, url_name: str, rule: RateLimitRule) -> bool:
    if str(request.method).upper() not in rule.methods:
        return False

    cache_key = _build_rate_limit_key(request, url_name, rule)
    try:
        created = cache.add(cache_key, 1, timeout=rule.window_seconds)
        if created:
            return False
        current = int(cache.incr(cache_key))
    except ValueError:
        cache.set(cache_key, 1, timeout=rule.window_seconds)
        return False
    except Exception:
        failure_mode = getattr(settings, "RATE_LIMIT_CACHE_FAILURE_MODE", "closed")
        logger.exception(
            "Rate limit cache backend failed for url_name=%s failure_mode=%s",
            url_name,
            failure_mode,
        )
        return str(failure_mode).lower() == "closed"
    return current > rule.limit


def build_rate_limited_response(request: HttpRequest, message: str) -> HttpResponse:
    from clients.services.responses import ResponseHelper

    helper = ResponseHelper(request)
    if helper.expects_json:
        return helper.error(message=message, status=429)
    return HttpResponse(message, status=429)


class RateLimitMiddleware:
    """Apply path-name based rate limits to sensitive endpoints."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)

        url_name = match.url_name
        full_name = match.view_name
        configured_rules: dict[str, Any] = getattr(settings, "RATE_LIMITS", {})
        rule_config = configured_rules.get(str(full_name)) or configured_rules.get(str(url_name))
        if rule_config:
            rule = RateLimitRule(**rule_config)
            if is_rate_limited(request, str(full_name or url_name or "unknown"), rule):
                response = build_rate_limited_response(request, rule.message)
                retry_after = str(rule.window_seconds)
                response["Retry-After"] = retry_after
                response["X-RateLimit-Limit"] = str(rule.limit)
                response["X-RateLimit-Reset"] = str(
                    int(timezone.now().timestamp()) + rule.window_seconds
                )
                return response

        return self.get_response(request)


class PermissionsPolicyMiddleware:
    """Attach ``Permissions-Policy`` header when the setting is configured."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.header_value: str = getattr(settings, "SECURE_PERMISSIONS_POLICY", "")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if self.header_value and "Permissions-Policy" not in response:
            response["Permissions-Policy"] = self.header_value
        return response


class ContentSecurityPolicyMiddleware:
    """Attach a configured Content-Security-Policy header."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response
        self.header_value: str = getattr(settings, "LEGALIZE_CONTENT_SECURITY_POLICY", "")
        report_only = getattr(settings, "LEGALIZE_CSP_REPORT_ONLY", False)
        self.report_only: bool = str(report_only).lower() in {"1", "true", "yes", "on"}

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not self.header_value:
            return response

        header_name = (
            "Content-Security-Policy-Report-Only"
            if self.report_only
            else "Content-Security-Policy"
        )
        if header_name not in response:
            response[header_name] = self.header_value
        return response
