import logging
import uuid

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context, tenant_context

from Customers.models import Client, Domain
from BaseBillet.tasks import membership_renewal_reminder
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
    def create_waiting_tenant(self):
        """
        Possible de créer des tenant ici, tout est fait avec le PUBLIC
        """
        with schema_context('public'):
            waiting_tenant_count = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
            logger.info(f"Waiting tenant count: {waiting_tenant_count}")
            if waiting_tenant_count < 10 :
                logger.info("Create waiting tenant")
                # Création des tenants manquant pour avec une catégorie WAITING chaque nuit. Il en faut au minimum 10.
                for i in range(10 - waiting_tenant_count):
                    rand_uuid = uuid.uuid4().hex
                    tenant_waiting, created = Client.objects.get_or_create(
                        schema_name=f'{rand_uuid}',
                        name=f'waiting_{rand_uuid}',
                        categorie=Client.WAITING_CONFIG,
                    )
                    tenant_waiting.save()
                logger.info("Waiting tenant created")


    def send_task_membership_renewal_reminder(self):
        """
        Pour faire des actions dans les tenants, on utilise la tâche Celery classique.
        Rien ne peut être fait en dehors de PUBLIC dans les cron
        """
        membership_renewal_reminder.delay()

    def handle(self, *args, **options):
        self.create_waiting_tenant()
        self.send_task_membership_renewal_reminder()
