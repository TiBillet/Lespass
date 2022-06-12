from django.apps import AppConfig


class BasebilletConfig(AppConfig):
    name = 'BaseBillet'
    verbose_name = "Billetterie"

    def ready(self):
        import BaseBillet.signals
