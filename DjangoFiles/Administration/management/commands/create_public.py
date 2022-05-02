from os.path import exists

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from Customers.models import Client, Domain
import os


class Command(BaseCommand):

    def handle(self, *args, **options):
        tenant_public, created = Client.objects.get_or_create(
            schema_name='public',
            name=os.environ.get('PUBLIC'),
            on_trial=False,
            categorie=Client.ROOT,
        )
        tenant_public.save()

        domain_public, created = Domain.objects.get_or_create(
            domain= f'{os.getenv("DOMAIN")}',
            tenant = tenant_public,
            is_primary = True
        )
        domain_public.save()

        meta = os.getenv("META")
        if not meta:
            print("Quelle sera le sous domaine META ?")
            meta = input()


        tenant_meta, created = Client.objects.get_or_create(
            schema_name='meta',
            name=slugify(meta),
            on_trial=False,
            categorie=Client.META,
        )
        tenant_meta.save()


        domain_public, created = Domain.objects.get_or_create(
            domain= f'{slugify(meta)}.{os.getenv("DOMAIN")}',
            tenant = tenant_meta,
            is_primary = True
        )
        domain_public.save()