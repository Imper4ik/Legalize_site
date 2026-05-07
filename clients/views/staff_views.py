from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from clients.forms import StaffUserCreateForm, StaffUserUpdateForm
from clients.services.roles import (
    PEOPLE_ALLOWED_ROLES,
    PREDEFINED_ROLES,
    ensure_predefined_roles,
)
from clients.views.base import role_required_view


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
                # TODO(audit): add an organization-level audit/event log for employee permission changes
                # (actor=request.user, target=staff_user, changed_fields only, no PII) once such model exists.
                form.save()
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
            staff_user.is_active = not staff_user.is_active
            staff_user.save(update_fields=["is_active"])
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
