from django.apps import AppConfig

class InventConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invent'

    def ready(self):
        # Import signals so they are registered when Django starts
        try:
            import invent.signals  # noqa: F401
        except Exception:
            # Avoid breaking management commands during development if signals import fails
            pass