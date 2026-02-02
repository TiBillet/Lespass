import logging
import os

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from AuthBillet.utils import get_or_create_user
from BaseBillet.models import Configuration
from Customers.models import Client, Domain

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    # def add_arguments(self, parser):
    # Named (optional) arguments
    # parser.add_argument(
    #     '--tdd',
    #     action='store_true',
    #     help='Demo data for Test drived dev',
    # )

    def handle(self, *args, **options):
        # START MIGRATE AND INSTALL BEFORE THIS SCRIPT
        sub = os.environ['SUB']
        try :
            tenant1 = Client.objects.get(name=sub)
        except Client.DoesNotExist:
            logger.info(f"No tenant found with {sub}. Name changed : demo data already installed")
            return None

        tenant1.name = "Le Tiers-Lustre"
        tenant1.save()

        # Fabrication d'un deuxième tenant pour de la fédération
        with schema_context('public'):
            name = "Chantefrein"
            domain = os.getenv("DOMAIN")
            tenant, created = Client.objects.get_or_create(
                schema_name=slugify(name),
                name=name,
                on_trial=False,
                categorie=Client.SALLE_SPECTACLE,
            )
            Domain.objects.get_or_create(
                domain=f'{slugify(name)}.{domain}',
                tenant=tenant,
                is_primary=True
            )
            # Sans envoie d'email pour l'instant, on l'envoie quand tout sera bien terminé
            user: TibilletUser = get_or_create_user(os.environ['ADMIN_EMAIL'], send_mail=False)
            user.client_admin.add(tenant)
            user.is_staff = True
            user.save()

        tenant2 = Client.objects.get(name="Chantefrein")

        for tenant in [tenant1, tenant2]:
            config = Configuration.get_solo()
            config.stripe_connect_account_test = os.environ.get('TEST_STRIPE_CONNECT_ACCOUNT')
            config.stripe_payouts_enabled = True
            config.save()