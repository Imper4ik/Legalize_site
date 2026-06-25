from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest, HttpResponseForbidden
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _

from clients.services.access import is_internal_staff_user, user_has_internal_role
from clients.services.permissions import has_employee_permission
from clients.services.responses import ResponseHelper

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


def safe_redirect_target(request: HttpRequest) -> str | None:
    """Return a validated same-site ``next`` URL from the request, or None.

    Lets action views (add/edit payment, add/complete task) return the user to
    the page they came from (e.g. a case detail page) instead of always the
    client page, without opening an open-redirect.
    """

    candidate = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    request: HttpRequest

    def test_func(self) -> bool:
        return is_internal_staff_user(self.request.user)


def staff_required_view(view_func: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
    @wraps(view_func)
    @login_required
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        if not is_internal_staff_user(request.user):
            helper = ResponseHelper(request)
            if helper.expects_json:
                return helper.forbidden()
            return HttpResponseForbidden(_('Доступ запрещен'))
        return view_func(request, *args, **kwargs)

    return _wrapped


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    request: HttpRequest
    allowed_roles: list[str] = []

    def test_func(self) -> bool:
        return user_has_internal_role(self.request.user, *self.allowed_roles)


def role_required_view(*allowed_roles: str) -> Callable[[Callable[..., HttpResponseBase]], Callable[..., HttpResponseBase]]:
    def decorator(view_func: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
        @wraps(view_func)
        @login_required
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if not user_has_internal_role(request.user, *allowed_roles):
                helper = ResponseHelper(request)
                if helper.expects_json:
                    return helper.forbidden()
                return HttpResponseForbidden(_('Доступ запрещен (требуется роль: %s)') % ", ".join(allowed_roles))
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


class RoleOrFeatureRequiredMixin(RoleRequiredMixin):
    required_permission_name: str | None = None

    def test_func(self) -> bool:
        if super().test_func():
            return True
        if not self.required_permission_name:
            return False
        return has_employee_permission(self.request.user, self.required_permission_name)


def role_or_feature_required_view(permission_name: str, *allowed_roles: str) -> Callable[[Callable[..., HttpResponseBase]], Callable[..., HttpResponseBase]]:
    def decorator(view_func: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
        @wraps(view_func)
        @login_required
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if user_has_internal_role(request.user, *allowed_roles) or has_employee_permission(request.user, permission_name):
                return view_func(request, *args, **kwargs)
            helper = ResponseHelper(request)
            if helper.expects_json:
                return helper.forbidden()
            return HttpResponseForbidden(_('Доступ запрещен'))

        return _wrapped

    return decorator
