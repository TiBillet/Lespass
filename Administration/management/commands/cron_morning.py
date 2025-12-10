import logging
import uuid

from django.core.management.base import BaseCommand
from django.db import connection
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
            needed = 20 - waiting_tenant_count

            if needed <= 0:
                logger.info("No waiting tenant needed.")
                return None

            logger.info(f"Creating {needed} waiting tenants...")
            for i in range(needed):
                rand_uuid = uuid.uuid4().hex
                tenant_waiting = Client(
                    schema_name=rand_uuid,
                    name=f'waiting_{rand_uuid}',
                    categorie=Client.WAITING_CONFIG,
                )
                tenant_waiting.auto_create_schema = False
                tenant_waiting.save()
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{rand_uuid}";')

            return True

    def run_waiting_migrations(self):
        import subprocess, sys, logging
        logger = logging.getLogger(__name__)

        logger.info("Launching tenant migrations with multiprocessing...")

        try:
            # Ne pas capturer stdout/stderr pour laisser s'afficher la sortie du process dans le terminal
            subprocess.run(
                [sys.executable, "manage.py", "migrate_schemas", "--executor=multiprocessing"],
                check=True,
            )
            logger.info("Migrations completed successfully.")
        except subprocess.CalledProcessError as e:
            # Quand on n'intercepte pas stdout/stderr, ils sont None.
            # Les détails de l'erreur ont déjà été affichés dans le terminal par le sous-processus.
            logger.error("Migration error (return code: %s). Voir la sortie ci-dessus pour les détails.", e.returncode)
            raise e



    def send_task_membership_renewal_reminder(self):
        """
        Pour faire des actions dans les tenants, on utilise la tâche Celery classique.
        Rien ne peut être fait en dehors de PUBLIC dans les cron
        """
        membership_renewal_reminder.delay()

    def handle(self, *args, **options):
        need_migration = self.create_waiting_tenant()
        if need_migration:
            self.run_waiting_migrations()

        self.send_task_membership_renewal_reminder()
