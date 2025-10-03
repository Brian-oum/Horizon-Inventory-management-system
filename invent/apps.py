from django.apps import AppConfig

class InventConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invent'

    def ready(self):
        import invent.signals 