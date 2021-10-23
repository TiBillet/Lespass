import os

from django.core.management.base import BaseCommand
from Customers.models import Client, Domain


class Command(BaseCommand):

    def handle(self, *args, **options):

        # create your public tenant
        tenant = Client(schema_name='public',
                        name='TiBillet Coop.',
                        paid_until='2242-12-05',
                        on_trial=False)
        tenant.save()

        # Add one or more domains for the tenant
        domain = Domain()
        domain.domain = f'{os.getenv("DOMAIN")}'  # don't add your port or www here! on a local server you'll want to use localhost here
        domain.tenant = tenant
        domain.is_primary = True
        domain.save()

        tenant_demo = Client.objects.get_or_create(schema_name="demo",
                                                       name="demo",
                                                       paid_until='2200-12-05',
                                                       on_trial=False)[0]

        # Add one or more domains for the tenant

        tenant_demo_domain = Domain.objects.get_or_create(domain=f'demo.{os.getenv("DOMAIN")}',
                                     tenant=tenant_demo,
                                     is_primary=True,
                                     )


