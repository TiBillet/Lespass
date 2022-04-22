from django.db import models, connection

# Create your models here.
from solo.models import SingletonModel


# Besoin du model de config pour email celery génral
class Configuration(SingletonModel):
    def uuid(self):
        return connection.tenant.pk

    email = models.EmailField(default="contact@tibillet.re")