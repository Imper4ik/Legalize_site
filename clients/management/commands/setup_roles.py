"""Management command to set up predefined roles and permissions."""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from clients.models import Client, Document, Payment, StaffTask


class Command(BaseCommand):
    help = "Creates predefined roles (Groups) and assigns permissions."

    def handle(self, *args, **options):
        roles = {
            "Admin": "All permissions (Superuser equivalent)",
            "Manager": "CRUD clients, documents, payments, tasks; send emails; view metrics",
            "Staff": "View/edit clients, upload documents, manage tasks",
            "ReadOnly": "View clients and documents only",
            "Translator": "Access to Translation Studio only",
        }

        for role_name, description in roles.items():
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created role: {role_name}"))
            else:
                self.stdout.write(f"Role already exists: {role_name}")

        self._assign_permissions()

    def _assign_permissions(self):
        # Admin gets everything (usually handled by is_superuser flag, but we can assign all perms)
        admin_group = Group.objects.get(name="Admin")
        admin_group.permissions.set(Permission.objects.all())

        # Manager
        manager_group = Group.objects.get(name="Manager")
        manager_perms = []
        for model in [Client, Document, Payment, StaffTask]:
            ct = ContentType.objects.get_for_model(model)
            manager_perms.extend(Permission.objects.filter(content_type=ct))
        manager_group.permissions.set(manager_perms)

        # Staff
        staff_group = Group.objects.get(name="Staff")
        staff_perms = []
        for model in [Client, Document, StaffTask]:
            ct = ContentType.objects.get_for_model(model)
            # Exclude delete permissions
            staff_perms.extend(Permission.objects.filter(content_type=ct).exclude(codename__startswith="delete_"))
        staff_group.permissions.set(staff_perms)

        # ReadOnly
        readonly_group = Group.objects.get(name="ReadOnly")
        readonly_perms = []
        for model in [Client, Document]:
            ct = ContentType.objects.get_for_model(model)
            readonly_perms.extend(Permission.objects.filter(content_type=ct, codename__startswith="view_"))
        readonly_group.permissions.set(readonly_perms)

        # Translator (assuming translation app has a specific model or view)
        # Often handled by simple is_staff + specific group check in the view.
        # We'll create the group but specific permissions depend on the translation package.

        self.stdout.write(self.style.SUCCESS("Assigned permissions to roles."))
