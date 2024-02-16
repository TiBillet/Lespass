from django.core.cache import cache
from django.db import models
from django_tenants.utils import schema_context
from solo.models import SingletonModel
from uuid import uuid4
from root_billet.models import RootConfiguration


class FedowConfig(SingletonModel):
    # rsa_key = models.OneToOneField(RsaKey, on_delete=models.CASCADE, null=True, blank=True)

    fedow_place_uuid = models.UUIDField(blank=True, null=True, editable=False)
    fedow_place_wallet_uuid = models.UUIDField(blank=True, null=True, editable=False)

    fedow_place_admin_apikey = models.CharField(max_length=41, blank=True, null=True, editable=False)
    fedow_place_wallet_public_pem = models.CharField(max_length=500, blank=True, null=True, editable=False)

    def fedow_domain(self):
        if cache.get('conf_root'):
            conf_root = cache.get('conf_root')
            return conf_root.fedow_domain

        with schema_context('public'):
            conf_root = RootConfiguration.get_solo()
            cache.set("conf_root", conf_root, 3600 * 24 * 30)
            return conf_root.fedow_domain

    def fedow_ip(self):
        if cache.get('conf_root'):
            conf_root = cache.get('conf_root')
            return conf_root.fedow_ip

        with schema_context('public'):
            conf_root = RootConfiguration.get_solo()
            cache.set("conf_root", conf_root, 3600 * 24 * 30)
            return conf_root.fedow_ip
