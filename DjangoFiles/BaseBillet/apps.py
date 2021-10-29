from django.apps import AppConfig


class BasebilletConfig(AppConfig):
    name = 'BaseBillet'

    def ready(self):
        import BaseBillet.signals
