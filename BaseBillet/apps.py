from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BasebilletConfig(AppConfig):
    name = 'BaseBillet'
    verbose_name = _("Ticketing")

    def ready(self):
        import BaseBillet.signals
