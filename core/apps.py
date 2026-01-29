"""Core app configuration."""
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core'
    
    def ready(self):
        """Import signals when app is ready."""
        # Import audit signals to register them
        try:
            from . import audit_signals  # noqa: F401
        except ImportError:
            pass
