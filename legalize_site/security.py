from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from ipaddress import ip_address
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
    # When True, a cache backend failure blocks the request regardless of the
    # global RATE_LIMIT_CACHE_FAILURE_MODE. Use for auth-sensitive endpoints so
    # a cache outage cannot silently disable brute-force protection.
    fail_closed: bool = False


def _normalized_ip(value: Any) -> str:
    try:
        return str(ip_address(str(value).strip()))
    except ValueError:
        return ""


def _client_ip(request: HttpRequest) -> str:
    remote_addr = _normalized_ip(request.META.get("REMOTE_ADDR")) or "unknown"

    if getattr(settings, "TRUST_RAILWAY_CLIENT_IP", False):
        railway_ip = _normalized_ip(request.META.get("HTTP_X_REAL_IP"))
        if railway_ip:
            return railway_ip

    trusted_proxies = {
        normalized for item in getattr(settings, "TRUSTED_PROXY_IPS", ()) if (normalized := _normalized_ip(item))
    }
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
    if forwarded_for and remote_addr in trusted_proxies:
        forwarded_ip = _normalized_ip(forwarded_for.split(",")[0])
        if forwarded_ip:
            return forwarded_ip
    return remote_addr


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
        failure_mode = "closed" if rule.fail_closed else getattr(settings, "RATE_LIMIT_CACHE_FAILURE_MODE", "closed")
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
                response["X-RateLimit-Reset"] = str(int(timezone.now().timestamp()) + rule.window_seconds)
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
        # Optional stricter policy emitted in Report-Only mode alongside the
        # enforced one. Lets us inventory inline-script/style violations before
        # dropping 'unsafe-inline' for real (the A3 hardening path).
        self.strict_report_only_value: str = getattr(settings, "LEGALIZE_CONTENT_SECURITY_POLICY_REPORT_ONLY", "")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Per-request nonce for inline <script nonce="{{ request.csp_nonce }}">.
        # Set before the view renders so templates can read it. The enforced
        # policy still carries 'unsafe-inline' (nothing breaks); the nonce makes
        # the strict report-only policy pass for our inline scripts, so the
        # eventual drop of 'unsafe-inline' can be validated against clean
        # telemetry (the A3 hardening path).
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce  # type: ignore[attr-defined]

        response = self.get_response(request)
        if self.header_value:
            header_name = "Content-Security-Policy-Report-Only" if self.report_only else "Content-Security-Policy"
            if header_name not in response:
                policy = self.header_value
                # Bind the per-request nonce to script-src so inline scripts that
                # carry nonce="{{ request.csp_nonce }}" execute under a policy that
                # no longer needs 'unsafe-inline' for scripts (audit P-02).
                if "script-src " in policy and "'nonce-" not in policy:
                    policy = policy.replace("script-src ", f"script-src 'nonce-{nonce}' ", 1)
                response[header_name] = policy

        # Attach the strict report-only policy only when the main policy is being
        # enforced, to avoid emitting two competing Report-Only headers.
        if self.strict_report_only_value and not self.report_only:
            if "Content-Security-Policy-Report-Only" not in response:
                strict_policy = self.strict_report_only_value.replace(
                    "script-src 'self'", f"script-src 'self' 'nonce-{nonce}'"
                )
                # Nonced <style> blocks pass the strict policy the same way
                # nonced scripts do, so the remaining style telemetry is only
                # about style="..." attributes (the A3 migration backlog).
                strict_policy = strict_policy.replace("style-src 'self'", f"style-src 'self' 'nonce-{nonce}'")
                response["Content-Security-Policy-Report-Only"] = strict_policy
        return response
