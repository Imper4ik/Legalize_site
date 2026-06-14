from __future__ import annotations

from typing import Any, cast

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from clients.forms import EMPLOYEE_PERMISSION_FIELD_LABELS, StaffUserCreateForm, StaffUserUpdateForm
from clients.models import EmployeePermission, StaffAuditEvent
from clients.services.roles import (
    PEOPLE_ALLOWED_ROLES,
    PREDEFINED_ROLES,
    ensure_predefined_roles,
)
from clients.views.base import role_required_view

STAFF_AUDIT_PROFILE_FIELDS = ("email", "first_name", "last_name", "is_staff", "is_active")


def _staff_update_snapshot(staff_user: Any) -> dict[str, Any]:
    permission_object = EmployeePermission.objects.filter(user=staff_user).first()
    permissions = {
        field_name: bool(getattr(permission_object, field_name, False))
        for field_name, _label in EMPLOYEE_PERMISSION_FIELD_LABELS
    }
    return {
        "profile": {field_name: getattr(staff_user, field_name) for field_name in STAFF_AUDIT_PROFILE_FIELDS},
        "groups": set(staff_user.groups.values_list("name", flat=True)),
        "permissions": permissions,
    }


def _log_staff_update_audit(*, actor: Any, target: Any, before: dict[str, Any]) -> None:
    after = _staff_update_snapshot(target)
    before_profile = before["profile"]
    after_profile = after["profile"]
    before_groups = before["groups"]
    after_groups = after["groups"]
    before_permissions = before["permissions"]
    after_permissions = after["permissions"]

    profile_fields_changed = [
        field_name
        for field_name in STAFF_AUDIT_PROFILE_FIELDS
        if before_profile[field_name] != after_profile[field_name]
    ]
    permission_changes = {
        field_name: {
            "old": before_permissions[field_name],
            "new": after_permissions[field_name],
        }
        for field_name, _label in EMPLOYEE_PERMISSION_FIELD_LABELS
        if before_permissions[field_name] != after_permissions[field_name]
    }
    groups_added = sorted(after_groups - before_groups)
    groups_removed = sorted(before_groups - after_groups)

    if not profile_fields_changed and not permission_changes and not groups_added and not groups_removed:
        return

    changed_fields = [
        *profile_fields_changed,
        *(f"permission:{field_name}" for field_name in permission_changes),
    ]
    if groups_added or groups_removed:
        changed_fields.append("groups")

    StaffAuditEvent.objects.create(
        actor=cast(Any, actor) if getattr(actor, "is_authenticated", False) else None,
        target=target,
        event_type=StaffAuditEvent.EVENT_STAFF_UPDATED,
        summary=f"Staff user updated: user_id={target.pk}",
        metadata={
            "changed_fields": changed_fields,
            "profile_fields_changed": profile_fields_changed,
            "permission_changes": permission_changes,
            "groups_added": groups_added,
            "groups_removed": groups_removed,
        },
    )


@role_required_view(*PEOPLE_ALLOWED_ROLES)
def staff_manage_view(request: HttpRequest) -> HttpResponse:
    user_model = get_user_model()
    staff_users = list(user_model.objects.filter(is_staff=True).order_by("email"))
    edit_forms = [
        (staff_user, StaffUserUpdateForm(instance=staff_user, prefix=f"user-{staff_user.id}"))
        for staff_user in staff_users
    ]
    create_form = StaffUserCreateForm(prefix="create", initial={"is_staff": True, "is_active": True})

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            create_form = StaffUserCreateForm(request.POST, prefix="create")
            if create_form.is_valid():
                create_form.save()
                messages.success(request, _("Сотрудник создан."))
                return redirect("clients:staff_manage")
            messages.error(request, _("Не удалось создать сотрудника. Проверьте форму."))

        elif action == "update":
            user_id = request.POST.get("user_id")
            staff_user = get_object_or_404(user_model, pk=user_id, is_staff=True)
            form = StaffUserUpdateForm(request.POST, instance=staff_user, prefix=f"user-{staff_user.id}")
            if form.is_valid():
                before = _staff_update_snapshot(staff_user)
                saved_user = form.save()
                _log_staff_update_audit(actor=request.user, target=saved_user, before=before)
                messages.success(request, _("Сотрудник обновлён."))
                return redirect("clients:staff_manage")
            messages.error(request, _("Не удалось обновить сотрудника. Проверьте форму."))
            edit_forms = [
                (item, form if item.pk == staff_user.pk else StaffUserUpdateForm(instance=item, prefix=f"user-{item.id}"))
                for item in staff_users
            ]

        elif action == "toggle_active":
            user_id = request.POST.get("user_id")
            staff_user = get_object_or_404(user_model, pk=user_id, is_staff=True)
            old_is_active = staff_user.is_active
            staff_user.is_active = not staff_user.is_active
            staff_user.save(update_fields=["is_active"])
            StaffAuditEvent.objects.create(
                actor=cast(Any, request.user) if getattr(request.user, "is_authenticated", False) else None,
                target=staff_user,
                event_type=StaffAuditEvent.EVENT_STAFF_ACTIVE_TOGGLED,
                summary=f"Staff active status toggled: user_id={staff_user.pk}",
                metadata={
                    "changed_fields": ["is_active"],
                    "old": old_is_active,
                    "new": staff_user.is_active,
                },
            )
            messages.success(request, _("Статус сотрудника обновлён."))
            return redirect("clients:staff_manage")

    return render(
        request,
        "clients/staff_manage.html",
        {
            "staff_rows": edit_forms,
            "create_form": create_form,
        },
    )


@role_required_view(*PEOPLE_ALLOWED_ROLES)
def role_manage_view(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        ensure_predefined_roles()
        messages.success(request, _("Роли и права синхронизированы."))
        return redirect("clients:role_manage")

    ensure_predefined_roles()
    roles = []
    for role_name, description in PREDEFINED_ROLES.items():
        group = Group.objects.get(name=role_name)
        roles.append(
            {
                "name": role_name,
                "description": description,
                "members_count": group.user_set.count(),
                "permissions_count": group.permissions.count(),
                "members": list(group.user_set.order_by("email")[:8]),
            }
        )

    return render(
        request,
        "clients/role_manage.html",
        {"roles": roles},
    )
