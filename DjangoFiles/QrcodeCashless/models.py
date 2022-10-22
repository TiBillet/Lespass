import uuid

from django.db import models

# Create your models here.
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator

from Customers.models import Client as Customers_Client
from TiBillet import settings


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

    qty = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    card = models.ForeignKey(
        CarteCashless, related_name='assets', on_delete=models.PROTECT)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT)
    last_date_used = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['asset', 'card']]
        verbose_name = 'Asset'
        verbose_name_plural = 'Portefeuilles'

    def __str__(self):
        return f'{self.asset.name}, {self.qty}'

