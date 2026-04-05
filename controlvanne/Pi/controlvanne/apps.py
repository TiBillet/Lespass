from django.apps import AppConfig

class ControlvanneConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'controlvanne'
    def ready(self):
        from . import signals
