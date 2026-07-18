"""Privilege-containment guards for the staff-management screen (audit 2026-07).

The role change already keeps Managers off this screen entirely. These tests
cover the defense-in-depth layer that additionally protects the superuser
"owner" account from non-superuser Admin-group actors: no self/lateral
escalation to Admin and no owner lockout via edit or deactivate.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from clients.services.roles import ensure_predefined_roles

PASSWORD = "Xk9!vQ2mLp7wZ"


class StaffManagementHardeningTests(TestCase):
    def setUp(self) -> None:
        ensure_predefined_roles()
        user_model = get_user_model()
        self.admin_group = Group.objects.get(name="Admin")
        self.manager_group = Group.objects.get(name="Manager")
        # A non-superuser owner-equivalent account (Admin group).
        self.admin_user = user_model.objects.create_user(
            email="admin@example.com", password=PASSWORD, is_staff=True
        )
        self.admin_user.groups.add(self.admin_group)
        # The real owner.
        self.owner = user_model.objects.create_user(
            email="owner@example.com", password=PASSWORD, is_staff=True, is_superuser=True
        )
        self.user_model = user_model

    def test_admin_group_user_cannot_grant_admin_role(self) -> None:
        target = self.user_model.objects.create_user(
            email="target@example.com", password=PASSWORD, is_staff=True
        )
        target.groups.add(self.manager_group)
        self.client.force_login(self.admin_user)
        self.client.post(
            reverse("clients:staff_manage"),
            data={
                "action": "update",
                "user_id": target.id,
                f"user-{target.id}-email": "target@example.com",
                f"user-{target.id}-is_staff": "on",
                f"user-{target.id}-is_active": "on",
                f"user-{target.id}-groups": [self.admin_group.id],
            },
        )
        target.refresh_from_db()
        self.assertFalse(
            target.groups.filter(name="Admin").exists(),
            "A non-superuser must not be able to grant the Admin (owner) role.",
        )

    def test_admin_group_user_cannot_deactivate_superuser_owner(self) -> None:
        self.client.force_login(self.admin_user)
        self.client.post(
            reverse("clients:staff_manage"),
            data={"action": "toggle_active", "user_id": self.owner.id},
        )
        self.owner.refresh_from_db()
        self.assertTrue(
            self.owner.is_active,
            "A non-superuser must not be able to deactivate the superuser owner.",
        )

    def test_admin_group_user_cannot_edit_superuser_owner(self) -> None:
        self.client.force_login(self.admin_user)
        self.client.post(
            reverse("clients:staff_manage"),
            data={
                "action": "update",
                "user_id": self.owner.id,
                f"user-{self.owner.id}-email": "hijacked@example.com",
                f"user-{self.owner.id}-is_staff": "on",
                f"user-{self.owner.id}-is_active": "on",
            },
        )
        self.owner.refresh_from_db()
        self.assertEqual(
            self.owner.email,
            "owner@example.com",
            "A non-superuser must not be able to edit the superuser owner.",
        )

    def test_superuser_can_still_grant_admin(self) -> None:
        target = self.user_model.objects.create_user(
            email="promote@example.com", password=PASSWORD, is_staff=True
        )
        self.client.force_login(self.owner)
        self.client.post(
            reverse("clients:staff_manage"),
            data={
                "action": "update",
                "user_id": target.id,
                f"user-{target.id}-email": "promote@example.com",
                f"user-{target.id}-is_staff": "on",
                f"user-{target.id}-is_active": "on",
                f"user-{target.id}-groups": [self.admin_group.id],
            },
        )
        target.refresh_from_db()
        self.assertTrue(target.groups.filter(name="Admin").exists())
