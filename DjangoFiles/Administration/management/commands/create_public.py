from os.path import exists

import stripe
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from Customers.models import Client, Domain
import os

from root_billet.models import RootConfiguration


class Command(BaseCommand):

    def handle(self, *args, **options):

        stripe_api_key = os.environ.get('STRIPE_KEY')
        stripe_test_api_key = os.environ.get('STRIPE_KEY_TEST')

        stripe_mode_test = True
        if os.environ.get('STRIPE_TEST') == "False":
            stripe_mode_test = False

        if not all([stripe_api_key, stripe_test_api_key]):
            raise Exception("Need Stripe Api Key in .env file")
        else :
            try :
                stripe.api_key = stripe_api_key
                stripe.Product.list()
                stripe.api_key = stripe_test_api_key
                stripe.Product.list()
            except:
                raise Exception("Stripe Api Key not valid")


        tenant_public, created = Client.objects.get_or_create(
            schema_name='public',
            name=os.environ.get('PUBLIC'),
            on_trial=False,
            categorie=Client.ROOT,
        )
        tenant_public.save()

        if not created:
            raise Exception("Public already installed")

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
            domain= f'm.{os.getenv("DOMAIN")}',
            tenant = tenant_meta,
            is_primary = False
        )
        domain_public.save()

        domain_public, created = Domain.objects.get_or_create(
            domain= f'{slugify(meta)}.{os.getenv("DOMAIN")}',
            tenant = tenant_meta,
            is_primary = True
        )
        domain_public.save()

        with tenant_context(tenant_public):
            rootConfig = RootConfiguration.get_solo()
            rootConfig.stripe_api_key = stripe_api_key
            rootConfig.stripe_test_api_key = stripe_test_api_key
            rootConfig.stripe_mode_test = stripe_mode_test
            rootConfig.save()