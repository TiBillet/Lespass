from os.path import exists

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from BaseBillet.models import ProductSold, PriceSold
from Customers.models import Client
from QrcodeCashless.models import Detail, CarteCashless
from django.core.validators import URLValidator

import csv, uuid




class Command(BaseCommand):
    for price in PriceSold.objects.all():
        price.id_price_stripe = None
        price.save()

    for prod in ProductSold.objects.all():
        prod.id_product_stripe = None
        prod.save()

