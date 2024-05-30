from os.path import exists
from time import sleep

import requests
import stripe
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import tenant_context

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from Customers.models import Client, Domain
import os

from fedow_connect.fedow_api import FedowAPI
from fedow_connect.models import FedowConfig
from root_billet.models import RootConfiguration

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    def add_arguments(self, parser):

        # Named (optional) arguments
        parser.add_argument(
            '--tdd',
            action='store_true',
            help='Demo data for Test drived dev',
        )

    def handle(self, *args, **options):

        # noinspection PyTestUnpassedFixture
        if Domain.objects.count() > 0:
            logger.warning("Public domain already installed")
            return "Public domain already installed -> continue"

        first_sub = os.environ['SUB']
        admin_email = os.environ['ADMIN_EMAIL']

        stripe_api_key = os.environ.get('STRIPE_KEY')
        stripe_test_api_key = os.environ.get('STRIPE_KEY_TEST')
        # Au moins une des deux clés.
        if not any([stripe_api_key, stripe_test_api_key]):
            raise Exception("Need Stripe Api Key in .env file")



        fedow_domain = os.getenv("FEDOW_DOMAIN")
        if not fedow_domain:
            raise Exception("Bad FEDOW_DOMAIN in .env file")

        fedow_state = None
        ping_count = 0
        while not fedow_state:
            hello_fedow = requests.get(f'https://{fedow_domain}/helloworld/',
                                       verify=bool(not settings.DEBUG))
            # Returns True if :attr:`status_code` is less than 400, False if not
            if hello_fedow.ok:
                fedow_state = hello_fedow.status_code
                self.stdout.write(
                    self.style.SUCCESS(f'ping fedow at {fedow_domain} OK'),
                    ending='\n')
            else :
                ping_count += 1
                self.stdout.write(
                    self.style.ERROR(f'ping fedow at https://{fedow_domain}/helloworld/ without succes. sleep(1) : count {ping_count}'),
                    ending='\n')
                sleep(1)


        # crash if bad api stripe key
        try:
            stripe_mode_test = True
            if os.environ.get('STRIPE_TEST') != '1':
                stripe_mode_test = False
                stripe.api_key = stripe_api_key
                # Test de la cléf
                stripe.Product.list()
            else:
                stripe.api_key = stripe_test_api_key
                stripe.Product.list()
        except Exception as e:
            raise e

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
            domain=f'{os.getenv("DOMAIN")}',
            tenant=tenant_public,
            is_primary=True
        )
        domain_public.save()

        ### Tenant générique : créer son espace !

        domain_public, created = Domain.objects.get_or_create(
            domain=f'www.{os.getenv("DOMAIN")}',
            tenant=tenant_public,
            is_primary=True
        )
        domain_public.save()

        ## Tenant META : tous les évènements de l'instance

        meta = os.getenv("META", 'agenda')
        tenant_meta, created = Client.objects.get_or_create(
            schema_name='meta',
            name=slugify(meta),
            on_trial=False,
            categorie=Client.META,
        )
        tenant_meta.save()

        domain_public, created = Domain.objects.get_or_create(
            domain=f'{slugify(meta)}.{os.getenv("DOMAIN")}',
            tenant=tenant_meta,
            is_primary=True
        )
        domain_public.save()

        ## m pour les scans de cartes,
        domain_public, created = Domain.objects.get_or_create(
            domain=f'm.{os.getenv("DOMAIN")}',
            tenant=tenant_meta,
            is_primary=False
        )
        domain_public.save()

        ### Installation du premier tenant :

        tenant_first_sub, created = Client.objects.get_or_create(
            schema_name=first_sub,
            name=slugify(first_sub),
            on_trial=False,
            categorie=Client.SALLE_SPECTACLE,
        )
        tenant_first_sub.save()

        tenant_first_sub_domain = Domain.objects.create(
            domain=f'{first_sub}.{os.getenv("DOMAIN")}',
            tenant=tenant_first_sub,
            is_primary=True
        )
        tenant_first_sub_domain.save()


        with tenant_context(tenant_public):
            rootConfig = RootConfiguration.get_solo()
            rootConfig.stripe_test_api_key = stripe_test_api_key
            rootConfig.stripe_mode_test = stripe_mode_test
            rootConfig.save()
            rootConfig.set_stripe_api(stripe_api_key)

            logger.info("Fedow handshake")
            rootConfig.root_fedow_handshake(fedow_domain)

        with tenant_context(tenant_first_sub):
            ## Création du premier admin:
            user: TibilletUser = get_or_create_user(admin_email)
            user.client_admin.add(tenant_first_sub)


        call_command('check_permissions')
