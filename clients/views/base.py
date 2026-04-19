from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _

from clients.services.responses import ResponseHelper


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


def staff_required_view(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            helper = ResponseHelper(request)
            if helper.expects_json:
                return helper.forbidden()
            return HttpResponseForbidden(_('Доступ запрещен'))
        return view_func(request, *args, **kwargs)

    return _wrapped


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles: list[str] = []

    def test_func(self):
        if self.request.user.is_superuser:
            return True
        if not self.allowed_roles:
            return self.request.user.is_staff
        return self.request.user.groups.filter(name__in=self.allowed_roles).exists()


def role_required_view(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            has_role = False
            if not allowed_roles:
                has_role = request.user.is_staff
            else:
                has_role = request.user.groups.filter(name__in=allowed_roles).exists()
                
            if not has_role:
                helper = ResponseHelper(request)
                if helper.expects_json:
                    return helper.forbidden()
                return HttpResponseForbidden(_('Доступ запрещен (требуется роль: %s)') % ", ".join(allowed_roles))
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
