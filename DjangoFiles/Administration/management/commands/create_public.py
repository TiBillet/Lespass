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


