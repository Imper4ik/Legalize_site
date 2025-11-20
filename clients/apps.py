# clients/apps.py
from django.apps import AppConfig


class ClientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clients'

    def ready(self):
        # Этот импорт для регистрации сигналов
        import clients.signals
