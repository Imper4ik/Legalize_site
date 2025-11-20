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
