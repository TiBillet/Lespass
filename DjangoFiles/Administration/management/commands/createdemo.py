import os

from django.core.management.base import BaseCommand
from Customers.models import Client, Domain


class Command(BaseCommand):

    def handle(self, *args, **options):

        tenant_demo = Client.objects.get_or_create(schema_name="demo",
                                                       name="demo",
                                                       paid_until='2200-12-05',
                                                       on_trial=False)[0]

        # Add one or more domains for the tenant

        tenant_demo_domain = Domain.objects.get_or_create(domain=f'demo.{os.getenv("DOMAIN")}',
                                     tenant=tenant_demo,
                                     is_primary=True,
                                     )




