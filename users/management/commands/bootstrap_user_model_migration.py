from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Marks users.0001_initial as applied when bootstrapping an existing auth_user table."

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())
        if "django_migrations" not in tables:
            self.stdout.write("Skipping user-model bootstrap: django_migrations table does not exist yet.")
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
                ["users", "0001_initial"],
            )
            if cursor.fetchone():
                self.stdout.write("users.0001_initial is already recorded.")
                return

            cursor.execute("SELECT 1 FROM django_migrations WHERE app = %s LIMIT 1", ["auth"])
            if cursor.fetchone() is None:
                self.stdout.write("Skipping user-model bootstrap: auth migrations have not been applied yet.")
                return

            required_tables = {"auth_user", "auth_user_groups", "auth_user_user_permissions"}
            missing_tables = sorted(required_tables.difference(tables))
            if missing_tables:
                self.stdout.write(
                    f"Skipping user-model bootstrap: missing existing auth tables: {', '.join(missing_tables)}."
                )
                return

            cursor.execute(
                "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, %s)",
                ["users", "0001_initial", timezone.now()],
            )

        self.stdout.write(self.style.SUCCESS("Recorded users.0001_initial for an existing auth_user table."))

