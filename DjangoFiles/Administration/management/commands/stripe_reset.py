from django.core.management.base import BaseCommand
from BaseBillet.models import ProductSold, PriceSold


class Command(BaseCommand):
    for price in PriceSold.objects.all():
        price.id_price_stripe = None
        price.save()

    for prod in ProductSold.objects.all():
        prod.id_product_stripe = None
        prod.save()
