import uuid

from django.db import models

# Create your models here.
from stdimage import StdImageField
from stdimage.validators import MaxSizeValidator

from Customers.models import Client as Customers_Client
from TiBillet import settings
from django.utils.translation import gettext_lazy as _

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
    slug = models.SlugField(max_length=50, unique=True, blank=True, null=True)

    def __str__(self):
        return self.base_url


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

    def __str__(self):
        return self.number
