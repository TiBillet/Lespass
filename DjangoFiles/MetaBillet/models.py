from django.db import models, connection

# Create your models here.
from solo.models import SingletonModel


from Customers.models import Client


'''
# Besoin du model de config pour email celery génral
class Configuration(SingletonModel):
    def uuid(self):
        return connection.tenant.pk

    email = models.EmailField(default="contact@tibillet.re")
'''


class EventDirectory(models.Model):
    datetime = models.DateTimeField()
    event_uuid = models.UUIDField()
    place = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="place")
    artist = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="artist")
