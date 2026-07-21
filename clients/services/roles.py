from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser


PREDEFINED_ROLES: dict[str, str] = {
    "Admin": "All permissions (Superuser equivalent). Owner role: manages staff, roles, company/legal settings and prices.",
    "Manager": "Head employee: full operational access to clients, documents, payments, tasks, emails, reports, action logs and OCR review. Cannot manage staff/roles, company legal & GDPR settings, or prices, and cannot grant the Admin role.",
    "Staff": "Office access: clients, documents, payments, tasks, emails, reports, exports. Can add and delete documents. No settings/templates, no action logs, no client deletions by default (the admin can grant client deletions per employee).",
    "ReadOnly": "View clients and documents only",
    "Translator": "Access to Translation Studio only",
}


ADMIN_PANEL_ALLOWED_ROLES = ("Admin", "Manager", "Staff", "ReadOnly")
# Staff/people, company legal & GDPR settings, document templates and prices are
# owner-only. The Manager ("head employee") runs day-to-day operations but must
# not be able to change who works in the office, the data-controller identity,
# the privacy policy shown to data subjects, or pricing — and must never be able
# to grant itself the Admin (owner-equivalent) role. Keeping these at ("Admin",)
# closes the privilege-escalation and owner-lockout paths (audit 2026-07).
SETTINGS_ALLOWED_ROLES = ("Admin",)
CRITICAL_SETTINGS_ALLOWED_ROLES = ("Admin",)
PEOPLE_ALLOWED_ROLES = ("Admin",)
# Operational overview/reports stay available to Staff (not "settings").
REPORTS_VIEW_ROLES = ("Admin", "Manager", "Staff")

CLIENT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
DOCUMENT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
SUBMISSION_EDIT_ROLES = ("Admin", "Manager", "Staff")
SUBMISSION_DELETE_ROLES = ("Admin", "Manager")
DOCUMENT_EDIT_ROLES = ("Admin", "Manager", "Staff")
# Staff can add and delete documents. Client deletions remain off for Staff by
# default; the admin grants those per employee (can_delete_clients) via staff
# management. The per-employee can_delete_documents grant still lets a
# non-Staff role (e.g. an individually trusted account) delete documents.
DOCUMENT_DELETE_ROLES = ("Admin", "Manager", "Staff")
TASK_MUTATION_ROLES = ("Admin", "Manager", "Staff")
PAYMENT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
EMAIL_MUTATION_ROLES = ("Admin", "Manager", "Staff")
EXPORT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
REPORT_MUTATION_ROLES = ("Admin", "Manager", "Staff")
TRANSLATION_ALLOWED_ROLES = ("Admin", "Translator")
CLIENT_EDIT_ROLES = CLIENT_MUTATION_ROLES
CLIENT_DELETE_ROLES = ("Admin", "Manager")
CHECKLIST_MANAGE_ROLES = ("Admin", "Manager", "Staff")
RESTORE_ALLOWED_ROLES = ("Admin", "Manager", "Staff")
# OCR review is NOT a Staff role capability: Staff gets it only via the
# per-employee EmployeePermission.can_run_ocr_review grant (spec §1).
OCR_REVIEW_ALLOWED_ROLES = ("Admin", "Manager")


def user_has_any_role(user: AbstractBaseUser | AnonymousUser | None, *role_names: str) -> bool:
    if user is None:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if not getattr(user, "is_staff", False):
        return False
    if not role_names:
        return bool(getattr(user, "is_staff", False))

    # Use the request-memoized group-name set so repeated role checks on one
    # page (navigation, guards, templatetags) do not each hit auth_group.
    from clients.services.access import _user_group_names

    return bool(_user_group_names(user) & frozenset(role_names))


def ensure_predefined_roles() -> list[Group]:
    # Import lazily to avoid import-order issues during Django app initialization.
    from clients.models import Client, Document, Payment, StaffTask

    groups: dict[str, Group] = {}
    for role_name in PREDEFINED_ROLES:
        group, _created = Group.objects.get_or_create(name=role_name)
        groups[role_name] = group

    groups["Admin"].permissions.set(Permission.objects.all())

    manager_perms: list[Permission] = []
    for model in [Client, Document, Payment, StaffTask]:
        ct = ContentType.objects.get_for_model(model)
        manager_perms.extend(Permission.objects.filter(content_type=ct))
    groups["Manager"].permissions.set(manager_perms)

    # Staff: add/change/view for all office models, plus document deletion.
    # Client/payment/task deletions stay off by default and are granted per
    # employee through EmployeePermission (can_delete_clients).
    staff_perms: list[Permission] = []
    for model in [Client, Document, Payment, StaffTask]:
        ct = ContentType.objects.get_for_model(model)
        model_perms = Permission.objects.filter(content_type=ct)
        if model is not Document:
            model_perms = model_perms.exclude(codename__startswith="delete_")
        staff_perms.extend(model_perms)
    groups["Staff"].permissions.set(staff_perms)

    readonly_perms: list[Permission] = []
    for model in [Client, Document]:
        ct = ContentType.objects.get_for_model(model)
        readonly_perms.extend(Permission.objects.filter(content_type=ct, codename__startswith="view_"))
    groups["ReadOnly"].permissions.set(readonly_perms)

    return list(groups.values())
