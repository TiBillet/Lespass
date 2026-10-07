import logging
import uuid

from django.core.management.base import BaseCommand
from django.db import connection
from django_tenants.utils import schema_context, tenant_context

from Customers.etat_des_migrations import schema_est_entierement_migre
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

    def migrer_les_emplacements_pas_a_jour(self):
        """
        Migre chaque emplacement vide (`WAITING_CONFIG`) dont le schéma n'est pas à jour.
        / Migrates every empty WAITING_CONFIG slot whose schema is not up to date.

        On passe sur TOUS les emplacements, pas seulement ceux créés ce matin. Un
        emplacement resté à moitié migré (migration interrompue par un interblocage,
        tâche tuée) est ainsi réparé le lendemain. Un emplacement déjà à jour est
        sauté sans lancer de migration (vérification en un dixième de seconde environ).
        / Every slot, not only today's: a half-migrated slot gets repaired the next day.

        Les migrations se font une par une, dans un sous-processus. Une migration en
        échec est journalisée et n'arrête pas les suivantes.
        / One by one, in a subprocess. A failure is logged and does not stop the others.

        :return: la liste des schémas dont la migration a échoué (list de str)
        """
        import subprocess, sys

        with schema_context('public'):
            schemas_des_emplacements = list(
                Client.objects.filter(categorie=Client.WAITING_CONFIG)
                .order_by('created_on', 'pk')
                .values_list('schema_name', flat=True)
            )

        schemas_en_echec = []
        for schema_name in schemas_des_emplacements:
            # Toute erreur (vérification, création du schéma, migration) est isolée :
            # les emplacements suivants et le rappel d'adhésion passent quand même.
            # / Any error is isolated: next slots and the reminder still run.
            try:
                if schema_est_entierement_migre(schema_name):
                    continue

                logger.info(f"Migrating schema: {schema_name}")

                # `migrate_schemas --schema` refuse un schéma qui n'existe pas.
                # / `migrate_schemas --schema` refuses a missing schema.
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";')

                subprocess.run(
                    [sys.executable, "manage.py", "migrate_schemas", "--schema", schema_name],
                    check=True,
                )
                logger.info(f"Schema {schema_name} migrated successfully.")
            except Exception:
                logger.exception(f"Migration failed for schema {schema_name}.")
                schemas_en_echec.append(schema_name)

        return schemas_en_echec

    def send_task_membership_renewal_reminder(self):
        """
        Pour faire des actions dans les tenants, on utilise la tâche Celery classique.
        Rien ne peut être fait en dehors de PUBLIC dans les cron
        """
        membership_renewal_reminder.delay()

    def handle(self, *args, **options):
        self.create_waiting_tenant()
        schemas_en_echec = self.migrer_les_emplacements_pas_a_jour()

        # Le rappel part même si une migration a échoué : il ignore les emplacements
        # vides et ne dépend donc pas de leurs migrations.
        # / The reminder is sent even if a migration failed: it skips empty slots.
        self.send_task_membership_renewal_reminder()

        # On lève l'erreur à la fin, pour que la tâche Celery soit notée en échec.
        # L'emplacement en échec sera retenté demain matin.
        # / Raise at the end so the Celery task is marked as failed; retried tomorrow.
        if schemas_en_echec:
            raise Exception(
                f"cron_morning : migration en échec pour {len(schemas_en_echec)} "
                f"emplacement(s) : {', '.join(schemas_en_echec)}"
            )
