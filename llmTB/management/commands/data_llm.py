from django.core.management.base import BaseCommand
from BaseBillet.models import Product, OptionGenerale, Event, Tag
from Customers.models import Client

import csv


class Command(BaseCommand):
    def handle(self, *args, **options):
        big_data = {}
        with open('csv/all.csv', mode='w') as all_csv:
            all_csv_w = csv.writer(all_csv, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

            all_csv_w.writerow(['ARTISTE'])
            all_csv_w.writerow(['Nom', 'uuid'])
            for tenant in Client.objects.filter(categorie=Client.ARTISTE):
                all_csv_w.writerow([f'{tenant.name}', f'{tenant.uuid}'])

            all_csv_w.writerow(['SALLE DE SPECTACLE'])
            all_csv_w.writerow(['Nom', 'uuid'])
            for tenant in Client.objects.filter(categorie=Client.SALLE_SPECTACLE):
                all_csv_w.writerow([f'{tenant.name}', f'{tenant.uuid}'])

            all_csv_w.writerow(['PRODUITS'])
            all_csv_w.writerow(
                ['Nom', 'uuid', 'description', 'categorie'])
            products = Product.objects.all()
            for product in products:
                all_csv_w.writerow([f'{product.name}', f'{product.uuid}', f'{product.short_description}',
                                         f'{product.get_categorie_article_display()}'])

            all_csv_w.writerow(['TARIFS'])
            all_csv_w.writerow(['Nom', 'uuid', 'prix', 'description', 'produit abonnement obligatoire'])
            prices = product.prices.all()
            for price in prices:
                all_csv_w.writerow([f'{price.name}', f'{price.uuid}', f'{price.prix}', f'{price.short_description}',
                                       f'{price.adhesion_obligatoire}'])

            all_csv_w.writerow(['OPTIONS DE RESERVATIONS'])
            all_csv_w.writerow(['Nom', 'uuid'])
            for option in OptionGenerale.objects.all():
                all_csv_w.writerow([f'{option.name}', f'{option.uuid}'])

            all_csv_w.writerow(['TAGS'])
            all_csv_w.writerow(['Nom', 'uuid'])
            for tag in Tag.objects.all():
                all_csv_w.writerow([f'{tag.name}', f'{tag.uuid}'])

            all_csv_w.writerow(['CATEGORIES D\'EVENEMENTS'])
            all_csv_w.writerow(['Nom', 'id'])
            for categorie in Event.TYPE_CHOICES:
                all_csv_w.writerow([f'{categorie[1]}', f'{categorie[0]}'])
