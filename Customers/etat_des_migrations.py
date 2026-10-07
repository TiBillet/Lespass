"""
Savoir si le schéma d'un lieu a reçu toutes ses migrations.
/ Tell whether a venue schema has received all its migrations.

LOCALISATION : Customers/etat_des_migrations.py

UTILISÉ PAR :
- `Administration/management/commands/cron_morning.py` : chaque matin, on migre les
  emplacements vides (`WAITING_CONFIG`) qui ne sont pas à jour.
- `BaseBillet/validators.py` `TenantCreateValidator.create_tenant` : un nouveau lieu ne
  reçoit qu'un emplacement entièrement migré.

Un emplacement peut rester à moitié migré : une migration interrompue (interblocage
PostgreSQL, tâche Celery tuée) garde les migrations déjà terminées et s'arrête là. Un
emplacement peut aussi n'avoir qu'un schéma vide : `cron_morning` crée le schéma avant
de le migrer.
/ A slot can stay half-migrated (interrupted migration) or empty (schema created,
not yet migrated).
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django_tenants.utils import schema_context


def schema_est_entierement_migre(schema_name):
    """
    Renvoie True si toutes les migrations connues du code sont jouées dans ce schéma.
    / Returns True if every migration known to the code is applied in this schema.

    ÉTAPE 1 : la table `django_migrations` doit exister DANS ce schéma.
    C'est indispensable. Dans un lieu, le `search_path` vaut « <schéma>, public ».
    Si le schéma n'a pas sa propre table, Django lirait celle de `public` et
    répondrait « à jour » pour un schéma vide.
    / The table must exist IN this schema: otherwise the search_path would make
    Django read public's table and call an empty schema "up to date".

    ÉTAPE 2 : on demande à Django la liste des migrations qui restent à jouer. C'est
    le même calcul que `manage.py migrate --check`.
    / Same computation as `manage.py migrate --check`.

    :param schema_name: le nom du schéma PostgreSQL du lieu (str)
    :return: bool
    """
    # to_regclass renvoie NULL si la table ou le schéma n'existe pas (pas d'erreur).
    # / to_regclass returns NULL when the table or the schema does not exist.
    nom_complet_de_la_table = f'"{schema_name}".django_migrations'
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [nom_complet_de_la_table])
        table_des_migrations = cursor.fetchone()[0]

    if table_des_migrations is None:
        return False

    with schema_context(schema_name):
        executeur_de_migrations = MigrationExecutor(connection)
        dernieres_migrations_du_code = executeur_de_migrations.loader.graph.leaf_nodes()
        migrations_restant_a_jouer = executeur_de_migrations.migration_plan(
            dernieres_migrations_du_code
        )

    return len(migrations_restant_a_jouer) == 0
