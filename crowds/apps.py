from django.apps import AppConfig


class CrowdfundingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crowds'

    def ready(self):
        # Import signal handlers
        try:
            from . import signals  # noqa: F401
        except Exception:
            # Avoid crashing startup if migrations not applied yet
            pass
