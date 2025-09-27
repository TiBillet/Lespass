import logging

from django.core.cache import cache
from django.db import models
from django_tenants.utils import schema_context
from solo.models import SingletonModel

from fedow_connect.utils import fernet_decrypt, fernet_encrypt
from root_billet.models import RootConfiguration

logger = logging.getLogger(__name__)

#
# class Asset(models.Model):
#     # One asset per currency
#     uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_index=False)
#     name = models.CharField(max_length=100)
#     currency_code = models.CharField(max_length=3)
#     archive = models.BooleanField(default=False)
#
#     created_at = models.DateTimeField(default=timezone.now)
#     last_update = models.DateTimeField(auto_now=True, verbose_name=_("Dernière modification des informations de l'asset"))
#
#     comment = models.TextField(blank=True, null=True)
#
#     wallet_origin = models.ForeignKey('AuthBillet.Wallet', on_delete=models.PROTECT,
#                                       related_name='assets_created',
#                                       help_text=_("Lieu ou configuration d'origine"),
#                                       )
#
#     active = models.BooleanField(default=False,
#                                  verbose_name=_("Activer cet actif"),
#                                  help_text=_("Un lieux vous a peut être invité à partager cet actif ? Validez en cochant la case et sauvegardez.")
#                                  )
#
#     invitation_to_federated_with = models.ManyToManyField(Client,
#                                                           related_name="invitation_to_federated_with",
#                                                           blank=True,
#                                                           verbose_name=_("Inviter un lieux à partager cet actif"),
#                                                           help_text=_("Ajoutez un lieux a partager cet actif, il recevra un mail de confirmation. Une fois validé, il disparaitra de cette liste pour aller dans celle ci dessous"),
#                                                           )
#
#     federated_with = models.ManyToManyField(Client,
#                                             related_name="federated_assets",
#                                             verbose_name=_("Lieux fédérés"),
#                                             help_text=_("Lieux fédérés"),
#                                             blank=True, )
#
#     STRIPE_FED_FIAT = 'FED'
#     TOKEN_LOCAL_FIAT = 'TLF'
#     TOKEN_LOCAL_NOT_FIAT = 'TNF'
#     TIME = 'TIM'
#     FIDELITY = 'FID'
#     BADGE = 'BDG'
#     SUBSCRIPTION = 'SUB'
#
#     CATEGORIES = [
#         (TOKEN_LOCAL_FIAT, _('Fiduciaire')),
#         (TOKEN_LOCAL_NOT_FIAT, _('Cadeau')),
#         (STRIPE_FED_FIAT, _('Fiduciaire fédérée')),
#         (TIME, _("Monnaie temps")),
#         (FIDELITY, _("Points de fidélité")),
#         (BADGE, _("Badgeuse/Pointeuse")),
#         (SUBSCRIPTION, _('Adhésion ou abonnement')),
#     ]
#
#     category = models.CharField(
#         max_length=3,
#         choices=CATEGORIES
#     )
#
#     # Primary and federated asset send to cashless on new connection
#     # On token of this asset is equivalent to 1 euro
#     # A Stripe Chekcout must be associated to the transaction creation money
#     id_price_stripe = models.CharField(max_length=30, blank=True, null=True, editable=False)
#
#     def __str__(self):
#         return f"{self.name} {self.currency_code}"
#
#     class Meta:
#         # Only one can be true :
#         constraints = [UniqueConstraint(fields=["category"],
#                                         condition=Q(category='FED'),
#                                         name="unique_stripe_primary_asset")]





class FedowConfig(SingletonModel):
    fedow_place_uuid = models.UUIDField(blank=True, null=True, editable=False)
    fedow_place_admin_apikey = models.CharField(max_length=200, blank=True, null=True, editable=False)

    wallet = models.ForeignKey('AuthBillet.Wallet', on_delete=models.CASCADE, blank=True, null=True,
                               related_name='place')
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
                self.fedow_place_wallet_uuid]):
            return True
        return False
