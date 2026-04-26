from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _

from clients.services.access import is_internal_staff_user, user_has_internal_role
from clients.services.permissions import has_employee_permission
from clients.services.responses import ResponseHelper


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return is_internal_staff_user(self.request.user)


def staff_required_view(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not is_internal_staff_user(request.user):
            helper = ResponseHelper(request)
            if helper.expects_json:
                return helper.forbidden()
            return HttpResponseForbidden(_('Доступ запрещен'))
        return view_func(request, *args, **kwargs)

    return _wrapped


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles: list[str] = []

    def test_func(self):
        return user_has_internal_role(self.request.user, *self.allowed_roles)


def role_required_view(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
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

    def test_func(self):
        if super().test_func():
            return True
        if not self.required_permission_name:
            return False
        return has_employee_permission(self.request.user, self.required_permission_name)


def role_or_feature_required_view(permission_name: str, *allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if user_has_internal_role(request.user, *allowed_roles) or has_employee_permission(request.user, permission_name):
                return view_func(request, *args, **kwargs)
            helper = ResponseHelper(request)
            if helper.expects_json:
                return helper.forbidden()
            return HttpResponseForbidden(_('Доступ запрещен'))

        return _wrapped

    return decorator
