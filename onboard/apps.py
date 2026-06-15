"""
Configuration de l'app onboard.
/ Configuration of the onboard app.

LOCALISATION: onboard/apps.py
"""

from django.apps import AppConfig


class OnboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "onboard"
    verbose_name = "Onboard wizard"

    def ready(self):
        # On importe les signaux pour qu'ils soient connectes au demarrage.
        # / Import signals so they get wired up at startup.
        from onboard import signals  # noqa: F401
