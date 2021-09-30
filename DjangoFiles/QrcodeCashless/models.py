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
    origine = models.ForeignKey(Customers_Client, on_delete=models.PROTECT, null=True, blank=True)
    generation = models.SmallIntegerField()

    def __str__(self):
        return self.base_url

class CarteCashless(models.Model):
    tag_id = models.CharField(
        db_index=True,
        max_length=8,
        unique=True
    )

    uuid = models.UUIDField(
        blank=True, null=True,
        verbose_name='Uuid',
    )

    number = models.CharField(
        db_index=True,
        max_length=8,
        unique=True
    )

    detail = models.ForeignKey(Detail, on_delete=models.CASCADE, null=True, blank=True)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

