import os

from django.core.management.base import BaseCommand
from Customers.models import Client, Domain
import os, json

class Command(BaseCommand):

    def handle(self, *args, **options):
        # create your public tenant
        assert os.environ.get('PUBLIC')
        tenants_dict = json.loads(os.environ.get('TENANTS'))
        assert tenants_dict

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

        tenants = json.loads(os.environ.get('TENANTS'))
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


