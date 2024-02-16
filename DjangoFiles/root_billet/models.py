from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

# Create your models here.
from solo.models import SingletonModel

from root_billet.utils import fernet_encrypt, fernet_decrypt


class RootConfiguration(SingletonModel):


    TZ_REUNION, TZ_PARIS = "Indian/Reunion", "Europe/Paris"
    TZ_CHOICES = [
        (TZ_REUNION, _('Indian/Reunion')),
        (TZ_PARIS, _('Europe/Paris')),
    ]

    fuseau_horaire = models.CharField(default=TZ_REUNION,
                                      max_length=50,
                                      choices=TZ_CHOICES,
                                      )

    stripe_api_key = models.CharField(max_length=110, blank=True, null=True)
    stripe_test_api_key = models.CharField(max_length=110, blank=True, null=True)

    stripe_mode_test = models.BooleanField(default=True)


    """
    FEDOW
    """

    fedow_domain = models.URLField(blank=True, null=True, editable=False)
    fedow_ip = models.GenericIPAddressField(blank=True, null=True, editable=False)
    fedow_create_place_apikey = models.CharField(max_length=110, blank=True, null=True, editable=False)

    def get_stripe_api(self):
        if self.stripe_mode_test:
            return self.stripe_test_api_key
        else:
            return fernet_decrypt(self.stripe_api_key)

    def set_stripe_api(self, string):
        self.stripe_api_key = fernet_encrypt(string)
        cache.clear()
        self.save()
        return True

    def set_fedow_create_place_apikey(self, string):
        self.fedow_create_place_apikey = fernet_encrypt(string)
        cache.clear()
        self.save()
        return True

    def get_fedow_create_place_apikey(self):
        return fernet_decrypt(self.fedow_create_place_apikey)

