import uuid

from django.db import models

# Create your models here.
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator

from Customers.models import Client as Customers_Client
from TiBillet import settings

import logging

logger = logging.getLogger(__name__)


class Detail(models.Model):
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
    federated_with = models.ManyToManyField(Customers_Client,
                                            blank=True,
                                            related_name="feredated_assets")

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
        editable=False
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

    # Un wallet DOIT avoir un user
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    sync = models.JSONField(null=True, blank=True)

    # card = models.ForeignKey(
    #     CarteCashless,
    #     on_delete=models.PROTECT,
    #     null=True, blank=True
    # )

    def __str__(self):
        return f'{self.asset.name}, {self.qty}'

    class Meta:
        unique_together = [['asset', 'user']]
