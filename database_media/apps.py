from __future__ import annotations

from django.apps import AppConfig


class DatabaseMediaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "database_media"
    verbose_name = "Database media storage"
