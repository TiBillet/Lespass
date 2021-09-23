from django.db import models

# Create your models here.
from Customers.models import Client as Customers_Client


class CarteCashless(models.Model):
    tag_id = models.CharField(
        db_index=True,
        max_length=8,
        unique=True
    )

    uuid_qrcode = models.UUIDField(
        blank=True, null=True,
        verbose_name='Uuid',
    )

    number = models.CharField(
        db_index=True,
        max_length=8,
        blank=True,
        null=True,
        unique=True
    )

    origine = models.ForeignKey(Customers_Client, on_delete=models.PROTECT)