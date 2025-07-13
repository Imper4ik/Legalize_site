# clients/apps.py

from django.apps import AppConfig

class ClientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'clients'

    def ready(self):
        # Эта строка импортирует и активирует наши сигналы
        import clients.signals