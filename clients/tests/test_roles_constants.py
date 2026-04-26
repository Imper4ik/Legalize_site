from __future__ import annotations

from clients.services import roles


def test_required_role_constants_are_exported_and_non_empty():
    required = (
        "CLIENT_EDIT_ROLES",
        "CLIENT_DELETE_ROLES",
        "CHECKLIST_MANAGE_ROLES",
        "DOCUMENT_EDIT_ROLES",
        "DOCUMENT_DELETE_ROLES",
    )

    for name in required:
        assert hasattr(roles, name), f"Missing roles constant: {name}"
        value = getattr(roles, name)
        assert isinstance(value, tuple), f"{name} should be a tuple"
        assert value, f"{name} should not be empty"


def test_checklist_manage_roles_are_restricted_to_admin_and_manager():
    assert roles.CHECKLIST_MANAGE_ROLES == ("Admin", "Manager")
