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


class InpolCredentialsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Allow access to users who can manage inPOL credentials.

    Staff members retain access, but projects that delegate permissions
    (e.g., via a custom group) can grant the inPOL account permissions
    without toggling ``is_staff``. This keeps the credential form reachable
    even if the admin account isn't marked as staff in production.
    """

    perm_codename = "clients.add_inpolaccount"

    def test_func(self):
        user = self.request.user
        return user.is_staff or user.has_perm(self.perm_codename)


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
