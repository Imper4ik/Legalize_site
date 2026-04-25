from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from clients.forms import StaffUserCreateForm, StaffUserUpdateForm
from clients.services.roles import ensure_predefined_roles


class StaffFormSuperuserProtectionTests(TestCase):
    def setUp(self):
        ensure_predefined_roles()
        user_model = get_user_model()
        self.admin = user_model.objects.create_user(email="admin@example.com", password="pass", is_staff=True)
        self.admin.groups.add(Group.objects.get(name="Admin"))

    def test_crm_admin_cannot_create_superuser_through_staff_form(self):
        form = StaffUserCreateForm(
            data={
                "email": "new-staff@example.com",
                "first_name": "A",
                "last_name": "B",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
                "password1": "strong-pass-123",
                "password2": "strong-pass-123",
            }
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertFalse(user.is_superuser)

    def test_crm_admin_cannot_update_user_to_superuser_through_staff_form(self):
        user_model = get_user_model()
        target = user_model.objects.create_user(email="target@example.com", password="pass", is_staff=True)
        form = StaffUserUpdateForm(
            data={
                "email": "target@example.com",
                "first_name": "T",
                "last_name": "U",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
            instance=target,
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertFalse(user.is_superuser)

    def test_existing_superuser_flag_cannot_be_changed_by_crm_form(self):
        user_model = get_user_model()
        target = user_model.objects.create_user(
            email="root@example.com",
            password="pass",
            is_staff=True,
            is_superuser=True,
        )
        form = StaffUserUpdateForm(
            data={
                "email": "root@example.com",
                "first_name": "R",
                "last_name": "O",
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
            },
            instance=target,
        )
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertTrue(user.is_superuser)
