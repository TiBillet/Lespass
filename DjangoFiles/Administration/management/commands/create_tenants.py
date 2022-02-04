from os.path import exists

from django.core.management.base import BaseCommand
from Customers.models import Client, Domain
import os


class Command(BaseCommand):

    def handle(self, *args, **options):
        tenant_public, created = Client.objects.get_or_create(
            schema_name='public',
            name=os.environ.get('PUBLIC'),
            on_trial=False,
            categorie=Client.META,
        )
        tenant_public.save()

        domain_public, created = Domain.objects.get_or_create(
            domain= f'{os.getenv("DOMAIN")}',
            tenant = tenant_public,
            is_primary = True
        )
        domain_public.save()

        input_file_find = False
        tenants = {}
        if exists("/DjangoFiles/data/csv/domains_and_cards.py"):
            print("/DjangoFiles/data/csv/domains_and_cards.py existe. On charge depuis ce fichier ?")
            input_file_find = input('Y ? \n')

        if input_file_find in ["Y","y","yes","YES"]:
            from data.domains_and_cards import domains
            tenants = domains

        for tenant in tenants :

            tenant_db, created = Client.objects.get_or_create(schema_name=tenant,
                                                           name=tenant,
                                                           )

            for domain_str in tenants[tenant]:
                # Add one or more domains for the tenant
                domain_db, created = Domain.objects.get_or_create(domain=domain_str,
                                             tenant=tenant_db,
                                             is_primary=True,
                                             )


