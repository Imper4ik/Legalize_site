from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, Group, Permission
from django.contrib.contenttypes.models import ContentType


PREDEFINED_ROLES: dict[str, str] = {
    "Admin": "All permissions (Superuser equivalent)",
    "Manager": "CRUD clients, documents, payments, tasks; send emails; view metrics",
    "Staff": "View/edit clients, upload documents, manage tasks",
    "ReadOnly": "View clients and documents only",
    "Translator": "Access to Translation Studio only",
}


ADMIN_PANEL_ALLOWED_ROLES = ("Admin", "Manager", "Staff", "ReadOnly")
SETTINGS_ALLOWED_ROLES = ("Admin", "Manager")
PEOPLE_ALLOWED_ROLES = ("Admin",)

CLIENT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
DOCUMENT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
TASK_MUTATION_ROLES = ("Admin", "Manager", "Staff")
PAYMENT_MUTATION_ROLES = ("Admin", "Manager")
EMAIL_MUTATION_ROLES = ("Admin", "Manager")
EXPORT_MUTATION_ROLES = ("Admin", "Manager")
REPORT_MUTATION_ROLES = ("Admin", "Manager")
TRANSLATION_ALLOWED_ROLES = ("Admin", "Translator")
CLIENT_EDIT_ROLES = CLIENT_MUTATION_ROLES
CLIENT_DELETE_ROLES = ("Admin", "Manager")
CHECKLIST_MANAGE_ROLES = DOCUMENT_MUTATION_ROLES


def user_has_any_role(user: AbstractBaseUser, *role_names: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_staff", False):
        return False
    if not role_names:
        return getattr(user, "is_staff", False)
    return user.groups.filter(name__in=role_names).exists()


def ensure_predefined_roles() -> list[Group]:
    # Import lazily to avoid import-order issues during Django app initialization.
    from clients.models import Client, Document, Payment, StaffTask

    groups: dict[str, Group] = {}
    for role_name in PREDEFINED_ROLES:
        group, _created = Group.objects.get_or_create(name=role_name)
        groups[role_name] = group

    groups["Admin"].permissions.set(Permission.objects.all())

    manager_perms = []
    for model in [Client, Document, Payment, StaffTask]:
        ct = ContentType.objects.get_for_model(model)
        manager_perms.extend(Permission.objects.filter(content_type=ct))
    groups["Manager"].permissions.set(manager_perms)

    staff_perms = []
    for model in [Client, Document, StaffTask]:
        ct = ContentType.objects.get_for_model(model)
        staff_perms.extend(Permission.objects.filter(content_type=ct).exclude(codename__startswith="delete_"))
    groups["Staff"].permissions.set(staff_perms)

    readonly_perms = []
    for model in [Client, Document]:
        ct = ContentType.objects.get_for_model(model)
        readonly_perms.extend(Permission.objects.filter(content_type=ct, codename__startswith="view_"))
    groups["ReadOnly"].permissions.set(readonly_perms)

    return list(groups.values())
