import uuid

from django.db import models

# Create your models here.
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator

from Customers.models import Client as Customers_Client
from TiBillet import settings

import logging

logger = logging.getLogger(__name__)



class Detail(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)
    img = StdImageField(upload_to='images/',
                        null=True, blank=True,
                        validators=[MaxSizeValidator(1920, 1920)],
                        variations={
                            'med': (480, 480),
                            'thumbnail': (150, 90),
                        },
                        delete_orphans=True,
                        verbose_name='Recto de la carte'
                        )

    img_url = models.URLField(null=True, blank=True)
    base_url = models.CharField(max_length=60, null=True, blank=True)
    origine = models.ForeignKey(Customers_Client, on_delete=models.PROTECT, null=True, blank=True,
                                related_name='origine')
    generation = models.SmallIntegerField()

    def __str__(self):
        return self.base_url


class Asset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    origin = models.ForeignKey(Customers_Client, on_delete=models.PROTECT)
    name = models.CharField(max_length=50, null=False, blank=False)
    is_federated = models.BooleanField(default=False)
    # federated_with = models.ManyToManyField(Customers_Client,
    #                                         blank=True,
    #                                         related_name="feredated_assets")

    class Meta:
        unique_together = [['origin', 'name']]

    def __str__(self):
        return self.name

class CarteCashless(models.Model):
    tag_id = models.CharField(
        db_index=True,
        max_length=8,
        unique=True,
        editable=False
    )

    uuid = models.UUIDField(
        blank=True, null=True,
        verbose_name='Uuid',
        unique=True,
        editable=False,
        db_index=True,
    )

    number = models.CharField(
        db_index=True,
        max_length=8,
        unique=True,
        editable=False
    )

    # Details communes des cartes cashless
    detail = models.ForeignKey(Detail, on_delete=models.CASCADE, null=True, blank=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)


class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    last_date_used = models.DateTimeField(auto_now=True)

    # Un wallet DOIT avoir un user ou une carte
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    # La carte seule est dans le cas d'un festival ou l'utilisateur n'a pas lié
    # son billet ni payé en ligne au moins une fois (email nécéssaire)
    card = models.ForeignKey(CarteCashless, on_delete=models.PROTECT, null=True, blank=True)

    sync = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f'{self.asset.name}, {self.qty}'

    class Meta:
        unique_together = [['asset', 'user']]

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        # On vérifie que le wallet possède soit un User, soit une carte.
        if self.user is None and self.card is None:
            raise ValueError('Wallet must have a user or a card')

        # Si la carte à un user, on l'associe au wallet
        if self.card.user is not None:
            if not self.user :
                self.user = self.card.user

            # Si l'utilisateur de la carte est différent de celui du wallet
            elif self.user != self.card.user:
                raise ValueError('Wallet user must be the same as the card user')

        super().save(force_insert, force_update, using, update_fields)


class FederatedCashless(models.Model):
    """
    On enregistre les tenants qui ont un cashless fédéré
    et on les lie à l'asset pour mieux le rechercher dans le futur
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    client = models.ForeignKey(Customers_Client, on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    server_cashless = models.URLField(null=True, blank=True)
    key_cashless = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        unique_together = [['client', 'asset']]

    def __str__(self):
        if self.server_cashless :
            return f'{self.client.name} : {self.server_cashless}'
        return f'{self.client.name}'

class SyncFederatedLog(models.Model):
    """
    On garde en memoire les logs des synchronisations avec les federations
    """
    uuid = models.UUIDField(default=uuid.uuid4)

    date = models.DateTimeField(auto_now_add=True)
    card = models.ForeignKey(CarteCashless, on_delete=models.CASCADE, null=True, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, null=True, blank=True)
    client_source = models.ForeignKey(Customers_Client, on_delete=models.CASCADE, null=True, blank=True)

    etat_client_sync = models.JSONField(null=True, blank=True)
    # Example :
    # {
    #   'tenant_uuid' : {'status': 'success', '200': 'Synchronisation réussie'},
    # }

    def get_federated_clients(self):
        federated_client = FederatedCashless.objects.filter(asset=self.asset)
        return federated_client

    def is_sync(self):
        try:
            for tenant in self.get_federated_clients():
                if self.etat_client_sync[tenant.client.uuid]['status'] != 200:
                    return False
        except Exception :
            return False
        return True


    def __str__(self):
        return f"{self.date}"