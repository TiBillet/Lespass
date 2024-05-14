import os
import requests
from django.conf import settings
from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _
import socket
from solo.models import SingletonModel
from root_billet.utils import fernet_encrypt, fernet_decrypt
import logging

logger = logging.getLogger(__name__)


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
    fedow_create_place_apikey = models.CharField(max_length=200, blank=True, null=True, editable=False)
    fedow_primary_pub_pem = models.CharField(max_length=500, blank=True, null=True, editable=False)

    def get_stripe_api(self):
        if self.stripe_mode_test:
            return os.environ.get('STRIPE_KEY_TEST')
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

    def root_fedow_handshake(self, fedow_domain):
        handshake = requests.get(f"https://{fedow_domain}/root_tibillet_handshake/", verify=(not settings.DEBUG))
        if handshake.status_code == 201:
            data = handshake.json()
            self.fedow_domain = fedow_domain
            self.fedow_ip = socket.gethostbyname(f"{fedow_domain}")
            # fernet encryption :
            self.set_fedow_create_place_apikey(data['api_key'])
            # Pub key of fedow primary wallet (stripe)
            self.fedow_primary_pub_pem = data['fedow_pub_pem']
            self.save()
            logger.info(f"TiBillet/Lespass registered in Fedow Instance")
            return True
        elif handshake.status_code == 208:
            logger.error(f"A TiBillet/Lespass is already registered in this fedow Instance")

        logger.error(f"Error while root handshake with FEDOW")
        raise Exception(f"Error while root handshake with FEDOW")
