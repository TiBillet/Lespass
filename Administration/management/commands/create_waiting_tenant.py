import logging
import uuid

from django.core.management.base import BaseCommand

from Customers.models import Client, Domain

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    def add_arguments(self, parser):


        # Named (optional) arguments
        parser.add_argument(
            '--tdd',
            action='store_true',
            help='Demo data for Test drived dev',
        )
    """

    def handle(self, *args, **options):

        waiting_tenant_count = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
        if waiting_tenant_count < 10 :
            # Création des tenants manquant pour avec une catégorie WAITING chaque nuit. Il en faut au minimum 10.
            for i in range(10 - waiting_tenant_count):
                rand_uuid = uuid.uuid4().hex
                tenant_waiting, created = Client.objects.get_or_create(
                    schema_name=f'{rand_uuid}',
                    name=f'waiting_{rand_uuid}',
                    categorie=Client.WAITING_CONFIG,
                )
                tenant_waiting.save()