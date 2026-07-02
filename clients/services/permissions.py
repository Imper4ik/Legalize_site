from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils.translation import gettext as _

from clients.services.access import is_internal_staff_user
from clients.services.responses import ResponseHelper
from clients.services.roles import user_has_any_role

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

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

READONLY_BLOCKED_PERMISSION_FIELDS = {
    "can_manage_payments",
    "can_send_custom_email",
    "can_send_mass_email",
    "can_export_clients",
    "can_delete_clients",
    "can_delete_documents",
    "can_manage_checklists",
    "can_manage_staff_tasks",
    "can_run_ocr_review",
}


def has_employee_permission(user: AbstractBaseUser | AnonymousUser | None, permission_name: str) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if user_has_any_role(user, "Admin"):
        return True
    if permission_name not in EMPLOYEE_PERMISSION_FIELDS:
        return False
    if not is_internal_staff_user(user):
        return False
    if user_has_any_role(user, "ReadOnly") and permission_name in READONLY_BLOCKED_PERMISSION_FIELDS:
        return False

    permission_object = getattr(user, "employee_permission", None)
    if permission_object is None:
        return False
    return bool(getattr(permission_object, permission_name, False))


def user_can_run_ocr_review(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    """OCR review capability check (spec §1).

    Admin/Manager have it by role; Staff only via the per-employee
    ``EmployeePermission.can_run_ocr_review`` grant.
    """
    from clients.services.roles import OCR_REVIEW_ALLOWED_ROLES

    return (
        user_has_any_role(user, *OCR_REVIEW_ALLOWED_ROLES)
        or has_employee_permission(user, "can_run_ocr_review")
    )


def user_can_delete_clients(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    """Mirror of the ClientDeleteView gate for template button visibility."""
    from clients.services.roles import CLIENT_DELETE_ROLES

    return (
        user_has_any_role(user, *CLIENT_DELETE_ROLES)
        or has_employee_permission(user, "can_delete_clients")
    )


def user_can_delete_documents(user: AbstractBaseUser | AnonymousUser | None) -> bool:
    """Mirror of the document_delete gate for template button visibility."""
    from clients.services.roles import DOCUMENT_DELETE_ROLES

    return (
        user_has_any_role(user, *DOCUMENT_DELETE_ROLES)
        or has_employee_permission(user, "can_delete_documents")
    )


def feature_permission_required(permission_name: str) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    def decorator(view_func: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view_func)
        @login_required
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not has_employee_permission(request.user, permission_name):
                helper = ResponseHelper(request)
                if helper.expects_json:
                    return helper.forbidden()
                return HttpResponseForbidden(_("Доступ запрещен"))
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
