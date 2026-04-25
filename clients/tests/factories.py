from __future__ import annotations

from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from clients.services.roles import ensure_predefined_roles


def create_role_user(role: str = "Staff", email: str | None = None, password: str = "pass"):
    ensure_predefined_roles()
    user_model = get_user_model()
    resolved_email = email or f"{role.lower()}-{uuid4().hex[:8]}@example.com"
    user = user_model.objects.create_user(
        email=resolved_email,
        password=password,
        is_staff=True,
    )
    user.groups.add(Group.objects.get(name=role))
    return user


def create_admin_user(email: str | None = None, password: str = "pass"):
    return create_role_user(role="Admin", email=email, password=password)


def create_manager_user(email: str | None = None, password: str = "pass"):
    return create_role_user(role="Manager", email=email, password=password)


def create_staff_user(email: str | None = None, password: str = "pass"):
    return create_role_user(role="Staff", email=email, password=password)


def create_readonly_user(email: str | None = None, password: str = "pass"):
    return create_role_user(role="ReadOnly", email=email, password=password)
