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
        Crée les tenants en attente jusqu'à atteindre le stock de 20.
        Retourne la liste des schema_name nouvellement créés,
        ou une liste vide si le stock est déjà suffisant.
        / Creates waiting tenants up to a stock of 20.
        Returns the list of newly created schema_names,
        or an empty list if the stock is already sufficient.
        """
        with schema_context('public'):
            waiting_tenant_count = Client.objects.filter(categorie=Client.WAITING_CONFIG).count()
            logger.info(f"Waiting tenant count: {waiting_tenant_count}")
            needed = 20 - waiting_tenant_count

            if needed <= 0:
                logger.info("No waiting tenant needed.")
                return []

            logger.info(f"Creating {needed} waiting tenants...")
            new_schema_names = []
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
                new_schema_names.append(rand_uuid)

            return new_schema_names

    def run_waiting_migrations(self, new_schema_names):
        """
        Migre uniquement les schemas nouvellement créés, un par un, de façon séquentielle.
        On évite ainsi de migrer les 300+ tenants existants et on réduit la contention
        de verrous PostgreSQL (max_locks_per_transaction).
        / Migrates only the newly created schemas, one by one, sequentially.
        This avoids migrating all 300+ existing tenants and reduces
        PostgreSQL lock contention (max_locks_per_transaction).
        """
        import subprocess, sys

        logger.info(f"Migrating {len(new_schema_names)} new tenant schemas sequentially...")

        for schema_name in new_schema_names:
            logger.info(f"Migrating schema: {schema_name}")
            try:
                subprocess.run(
                    [sys.executable, "manage.py", "migrate_schemas", "--schema", schema_name],
                    check=True,
                )
                logger.info(f"Schema {schema_name} migrated successfully.")
            except subprocess.CalledProcessError as e:
                logger.error(
                    "Migration failed for schema %s (return code: %s).",
                    schema_name, e.returncode
                )
                raise e

        logger.info("All new tenant schemas migrated successfully.")



    def send_task_membership_renewal_reminder(self):
        """
        Pour faire des actions dans les tenants, on utilise la tâche Celery classique.
        Rien ne peut être fait en dehors de PUBLIC dans les cron
        """
        membership_renewal_reminder.delay()

    def handle(self, *args, **options):
        new_schema_names = self.create_waiting_tenant()
        if new_schema_names:
            self.run_waiting_migrations(new_schema_names)

        self.send_task_membership_renewal_reminder()
