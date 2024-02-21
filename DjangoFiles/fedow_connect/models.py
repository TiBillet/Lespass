from django.core.cache import cache
from django.db import models
from django_tenants.utils import schema_context
from solo.models import SingletonModel

from root_billet.models import RootConfiguration


class FedowConfig(SingletonModel):
    # rsa_key = models.OneToOneField(RsaKey, on_delete=models.CASCADE, null=True, blank=True)

    fedow_place_uuid = models.UUIDField(blank=True, null=True, editable=False)
    fedow_place_wallet_uuid = models.UUIDField(blank=True, null=True, editable=False)

    fedow_place_admin_apikey = models.CharField(max_length=41, blank=True, null=True, editable=False)
    fedow_place_wallet_public_pem = models.CharField(max_length=500, blank=True, null=True, editable=False)

    def get_conf_root(self):
        if cache.get('conf_root'):
            conf_root = cache.get('conf_root')
            return conf_root

        with schema_context('public'):
            conf_root = RootConfiguration.get_solo()
            cache.set("conf_root", conf_root, 3600 * 24 * 30)
            return conf_root

    def fedow_domain(self):
        conf_root = self.get_conf_root()
        return conf_root.fedow_domain

    def fedow_ip(self):
        conf_root = self.get_conf_root()
        return conf_root.fedow_ip

    def get_fedow_create_place_apikey(self):
        # Si existe pas, doit être créé avec : set_fedow_create_place_apikey
        conf_root = self.get_conf_root()
        return conf_root.get_fedow_create_place_apikey()

    # def fedow_place_create(self):
    #     fedowAPI = FedowAPI(self)
    #     fedowAPI.place.create()
