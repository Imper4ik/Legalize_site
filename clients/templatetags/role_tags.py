from __future__ import annotations

from django import template

from clients.services.roles import user_has_any_role


register = template.Library()


@register.filter
def has_any_role(user, role_names: str) -> bool:
    roles = [role.strip() for role in (role_names or "").split(",") if role.strip()]
    return user_has_any_role(user, *roles)
