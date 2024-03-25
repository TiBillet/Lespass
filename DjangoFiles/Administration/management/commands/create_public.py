from os.path import exists

import stripe
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from Customers.models import Client, Domain
import os

from root_billet.models import RootConfiguration

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        def create_public():
            stripe_api_key = os.environ.get('STRIPE_KEY')
            stripe_test_api_key = os.environ.get('STRIPE_KEY_TEST')

            # Au moins une des deux clés.
            if not any([stripe_api_key, stripe_test_api_key]):
                raise Exception("Need Stripe Api Key in .env file")

            meta = os.getenv("META")
            if not meta:
                raise Exception("Need META in .env file")

            stripe_mode_test = True
            if os.environ.get('STRIPE_TEST') == "False" or os.environ.get('STRIPE_TEST') == 0:
                stripe_mode_test = False
                stripe.api_key = stripe_api_key
                # Test de la cléf
                stripe.Product.list()
            else:
                stripe.api_key = stripe_test_api_key
                stripe.Product.list()


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

            domain_public, created = Domain.objects.get_or_create(
                domain= f'www.{os.getenv("DOMAIN")}',
                tenant = tenant_public,
                is_primary = True
            )
            domain_public.save()

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


            call_command('check_permissions')

        try :
            Domain.objects.get(
                domain= f'{slugify(os.getenv("META"))}.{os.getenv("DOMAIN")}',
            )
            logger.warning("Public already installed")
        except Domain.DoesNotExist:
            create_public()