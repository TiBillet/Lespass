from django.conf import settings
from django.core.cache import cache
from django.db import models
from django_tenants.utils import schema_context
from solo.models import SingletonModel

from fedow_connect.utils import fernet_decrypt, fernet_encrypt
from root_billet.models import RootConfiguration


class FedowConfig(SingletonModel):
    fedow_place_uuid = models.UUIDField(blank=True, null=True, editable=False)
    fedow_place_admin_apikey = models.CharField(max_length=200, blank=True, null=True, editable=False)

    wallet = models.ForeignKey('AuthBillet.Wallet', on_delete=models.CASCADE, blank=True, null=True, related_name='place')
    fedow_place_wallet_uuid = models.UUIDField(blank=True, null=True, editable=False)

    json_key_to_cashless = models.CharField(max_length=500, editable=False, blank=True, null=True)

    def set_json_key_to_cashless(self, string):
        self.json_key_to_cashless = fernet_encrypt(string)
        cache.clear()
        self.save()

    def get_json_key_to_cashless(self):
        cypher = fernet_decrypt(self.json_key_to_cashless)
        # On efface la clé une fois qu'elle a été divulgée
        if not settings.DEBUG:
            self.json_key_to_cashless = None
            self.save()
        return cypher

    def set_fedow_place_admin_apikey(self, string):
        self.fedow_place_admin_apikey = fernet_encrypt(string)
        cache.clear()
        self.save()
        return True

    def get_fedow_place_admin_apikey(self):
        return fernet_decrypt(self.fedow_place_admin_apikey)

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
