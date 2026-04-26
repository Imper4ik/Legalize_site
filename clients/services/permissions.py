from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.utils.translation import gettext as _

from clients.models import EmployeePermission
from clients.services.access import is_internal_staff_user
from clients.services.responses import ResponseHelper
from clients.services.roles import user_has_any_role

EMPLOYEE_PERMISSION_FIELDS = {
    "can_manage_payments",
    "can_send_custom_email",
    "can_send_mass_email",
    "can_export_clients",
    "can_delete_clients",
    "can_delete_documents",
    "can_manage_checklists",
    "can_view_reports",
    "can_manage_staff_tasks",
    "can_run_ocr_review",
}


def has_employee_permission(user, permission_name: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user_has_any_role(user, "Admin"):
        return True
    if permission_name not in EMPLOYEE_PERMISSION_FIELDS:
        return False
    if not is_internal_staff_user(user):
        return False

    permission_object = getattr(user, "employee_permission", None)
    if permission_object is None:
        return False
    return bool(getattr(permission_object, permission_name, False))


def feature_permission_required(permission_name: str):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if not has_employee_permission(request.user, permission_name):
                helper = ResponseHelper(request)
                if helper.expects_json:
                    return helper.forbidden()
                return HttpResponseForbidden(_("Доступ запрещен"))
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
