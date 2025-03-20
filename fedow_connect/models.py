from django.conf import settings
from django.core.cache import cache
from django.db import models, connection
from django.utils.text import slugify
from django_tenants.utils import schema_context
from solo.models import SingletonModel

from fedow_connect.utils import fernet_decrypt, fernet_encrypt
from root_billet.models import RootConfiguration


class FedowConfig(SingletonModel):
    @classmethod
    def get_cache_key(cls) -> str:
        prefix = slugify(connection.tenant.pk)
        return f"{prefix}:{cls.__module__.lower()}:{cls.__name__.lower()}"

    fedow_place_uuid = models.UUIDField(blank=True, null=True, editable=False)
    fedow_place_admin_apikey = models.CharField(max_length=200, blank=True, null=True, editable=False)

    wallet = models.ForeignKey('AuthBillet.Wallet', on_delete=models.CASCADE, blank=True, null=True, related_name='place')
    fedow_place_wallet_uuid = models.UUIDField(blank=True, null=True, editable=False)

    def set_fedow_place_admin_apikey(self, string):
        self.fedow_place_admin_apikey = fernet_encrypt(string)
        cache.clear()
        self.save()
        return True

    def get_fedow_place_admin_apikey(self):
        return fernet_decrypt(self.fedow_place_admin_apikey)

    def get_conf_root(self):
        with schema_context('public'):
            conf_root = RootConfiguration.get_solo()
            return conf_root

    def fedow_domain(self):
        conf_root = self.get_conf_root()
        return conf_root.fedow_domain

    def fedow_ip(self):
        conf_root = self.get_conf_root()
        return conf_root.fedow_ip

    def get_fedow_create_place_apikey(self):
        # La clé unique pour création de place. Il ne peut en exister qu'une seule par FEDOW
        # Si existe pas, doit être créé avec à la main : ./manage.py root_fedow
        conf_root = self.get_conf_root()
        return conf_root.get_fedow_create_place_apikey()

    def can_fedow(self):
        if all([self.fedow_place_uuid,
                self.fedow_place_admin_apikey,
                self.fedow_place_wallet_uuid ]):
            return True
        return False
