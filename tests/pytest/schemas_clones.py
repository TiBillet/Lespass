"""
tests/pytest/schemas_clones.py — Créer les schémas de test par clonage d'un schéma modèle.
/ Create the test schemas by cloning a template schema.

LOCALISATION : tests/pytest/schemas_clones.py
Appelé par la fixture `_schema_de_test_cree_par_clonage` de tests/pytest/conftest.py.
/ Called by the `_schema_de_test_cree_par_clonage` fixture.

POURQUOI :
Chaque `FastTenantTestCase` a son schéma dédié (`get_test_schema_name`). Quand ce schéma
n'existe pas, django-tenants le crée en rejouant TOUTES les migrations : ~55 s par
schéma, ~40 min pour la suite complète après une base neuve.
Copier un schéma déjà migré prend quelques secondes.
/ WHY: each FastTenantTestCase has its own schema. A missing schema replays every
migration (~55 s each, ~40 min for the whole suite on a fresh database). Copying an
already migrated schema takes a few seconds.

FLUX :
1. `preparer_le_schema_modele()` : le schéma `test_modele` est créé par les migrations,
   une seule fois. Il est recréé si la liste des migrations du code a changé.
   Il n'a PAS de ligne `Client` : aucun lieu, aucune tâche ne l'utilise.
2. `creer_le_schema_par_clonage(nom)` : copie `test_modele` (tables, séquences ET
   données des migrations : plan comptable, taux de TVA…) avec la fonction SQL
   `clone_schema` de django-tenants, puis donne au nouveau schéma sa PROPRE clé
   d'empreinte.
3. Le `setUpClass` de django-tenants crée ensuite la ligne `Client` : il trouve le
   schéma déjà là (`create_schema(check_if_exists=True)`) et ne rejoue rien.
/ FLOW: 1. the template is built once by migrations, rebuilt if the code's migration
list changed; it has no Client row. 2. clone it (structure, sequences and migration
data), then give the clone its OWN fingerprint key. 3. django-tenants' setUpClass then
creates the Client row, finds the schema and replays nothing.

SEULEMENT EN TEST : ce module n'est appelé que par pytest, et seulement si TEST=1.
La création d'un lieu en dev, en préproduction ou en production ne change pas : elle
rejoue toujours les migrations.
/ TEST ONLY: venue creation in dev, preproduction and production is unchanged.
"""

from django.core.management import call_command
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django_tenants.clone import CloneSchema
from django_tenants.utils import schema_context, schema_exists

# Le schéma modèle. Il commence par « test_ » : c'est un schéma de test, jetable.
# / The template schema. Starts with "test_": a disposable test schema.
NOM_DU_SCHEMA_MODELE = "test_modele"


def lire_les_migrations_du_code():
    """
    Les migrations présentes dans le code, toutes applications confondues.
    / The migrations present in the code, all apps.

    :return: ensemble de couples (application, nom de la migration)
    """
    chargeur_de_migrations = MigrationLoader(None, ignore_no_migrations=True)
    return set(chargeur_de_migrations.disk_migrations.keys())


def lire_les_migrations_appliquees_au_modele():
    """
    Les migrations enregistrées dans la table `django_migrations` du schéma modèle.
    / The migrations recorded in the template schema's django_migrations table.

    :return: ensemble de couples (application, nom de la migration)
    """
    with connection.cursor() as curseur:
        curseur.execute(
            f'SELECT app, name FROM "{NOM_DU_SCHEMA_MODELE}".django_migrations'
        )
        lignes = curseur.fetchall()
    return set(lignes)


def le_modele_est_a_jour():
    """
    Vrai si le schéma modèle existe et a exactement les migrations du code.
    Une migration ajoutée, retirée ou renommée le périme.
    / True if the template exists and has exactly the code's migrations.
    """
    if not schema_exists(NOM_DU_SCHEMA_MODELE):
        return False

    migrations_du_code = lire_les_migrations_du_code()
    migrations_du_modele = lire_les_migrations_appliquees_au_modele()
    return migrations_du_code == migrations_du_modele


def preparer_le_schema_modele():
    """
    Garantit un schéma modèle à jour. Le (re)crée par les migrations si besoin (~55 s,
    une seule fois).
    / Ensures an up-to-date template schema. (Re)builds it by migrations if needed.

    La création passe par `migrate_schemas`, exactement comme la création d'un lieu :
    les migrations de données (`RunPython`) remplissent le modèle comme un lieu neuf.
    / Built by migrate_schemas, exactly like a venue creation.

    La clé d'empreinte écrite par la migration `laboutik 0002` est ensuite VIDÉE dans
    le modèle : aucune clé ne doit être copiée d'un schéma à l'autre.
    / The fingerprint key written by laboutik 0002 is then CLEARED in the template:
    no key may be copied from one schema to another.
    """
    connection.set_schema_to_public()

    if le_modele_est_a_jour():
        return

    print(
        f"\n[schemas_clones] Schéma modèle « {NOM_DU_SCHEMA_MODELE} » absent ou périmé : "
        f"création par les migrations (~1 min)."
    )

    with connection.cursor() as curseur:
        curseur.execute(f'DROP SCHEMA IF EXISTS "{NOM_DU_SCHEMA_MODELE}" CASCADE')
        curseur.execute(f'CREATE SCHEMA "{NOM_DU_SCHEMA_MODELE}"')

    call_command(
        "migrate_schemas",
        tenant=True,
        schema_name=NOM_DU_SCHEMA_MODELE,
        interactive=False,
        verbosity=0,
    )
    connection.set_schema_to_public()

    # Vider la clé d'empreinte du modèle. Chaque clone recevra la sienne.
    # / Clear the template's fingerprint key. Each clone gets its own.
    with connection.cursor() as curseur:
        curseur.execute(
            f'UPDATE "{NOM_DU_SCHEMA_MODELE}".laboutik_laboutikconfiguration '
            f"SET hmac_key = NULL"
        )


def reprendre_les_noms_du_modele(nom_du_schema):
    """
    Redonne aux contraintes et aux séquences du clone les noms qu'elles ont dans le modèle.
    / Gives the clone's constraints and sequences their names from the template.

    POURQUOI : `clone_schema` recrée les contraintes UNIQUE sous le nom par défaut de
    PostgreSQL (`<table>_<colonnes>_key`) au lieu du nom écrit par Django
    (`..._0e242bcf_uniq`, ou un nom choisi comme `unique_cloture_periode`) : 35 sur 437
    à la mesure. Il nomme aussi une séquence d'après le nom ACTUEL de sa table, alors
    qu'une table renommée par une migration garde son ancienne séquence
    (`BaseBillet_apikey_id_seq`). Sans ce renommage, le clone n'aurait pas les noms
    d'un lieu créé par les migrations.
    / WHY: clone_schema recreates UNIQUE constraints under PostgreSQL's default name and
    names a sequence after its table's current name. Without this, the clone would not
    have the names of a venue created by migrations.

    Une contrainte se reconnaît à sa table, son type et sa définition ; une séquence, à
    la colonne qui la possède (`serial` : dépendance 'a' ; `identity` : dépendance 'i'). Renommer une contrainte UNIQUE renomme aussi son index.
    / A constraint is matched by table, type and definition; a sequence, by its owning
    column. Renaming a UNIQUE constraint renames its index too.
    """
    requete_des_contraintes = """
        SELECT classe.relname, contrainte.contype, pg_get_constraintdef(contrainte.oid),
               contrainte.conname
        FROM pg_constraint contrainte
        JOIN pg_class classe ON classe.oid = contrainte.conrelid
        JOIN pg_namespace espace ON espace.oid = classe.relnamespace
        WHERE espace.nspname = %s
    """
    requete_des_sequences = """
        SELECT table_proprietaire.relname, colonne.attname, sequence.relname
        FROM pg_class sequence
        JOIN pg_namespace espace ON espace.oid = sequence.relnamespace
        JOIN pg_depend dependance ON dependance.objid = sequence.oid
            AND dependance.deptype IN ('a', 'i')
        JOIN pg_class table_proprietaire ON table_proprietaire.oid = dependance.refobjid
        JOIN pg_attribute colonne ON colonne.attrelid = dependance.refobjid
            AND colonne.attnum = dependance.refobjsubid
        WHERE espace.nspname = %s AND sequence.relkind = 'S'
    """

    with connection.cursor() as curseur:
        # 1. Les contraintes : (table, type, définition) -> nom.
        # / 1. Constraints: (table, type, definition) -> name.
        curseur.execute(requete_des_contraintes, [NOM_DU_SCHEMA_MODELE])
        nom_dans_le_modele = {}
        for table, type_de_contrainte, definition, nom in curseur.fetchall():
            nom_dans_le_modele[(table, type_de_contrainte, definition)] = nom

        curseur.execute(requete_des_contraintes, [nom_du_schema])
        contraintes_du_clone = curseur.fetchall()
        for table, type_de_contrainte, definition, nom_dans_le_clone in contraintes_du_clone:
            nom_attendu = nom_dans_le_modele.get((table, type_de_contrainte, definition))
            if nom_attendu is None or nom_attendu == nom_dans_le_clone:
                continue
            curseur.execute(
                f'ALTER TABLE "{nom_du_schema}"."{table}" '
                f'RENAME CONSTRAINT "{nom_dans_le_clone}" TO "{nom_attendu}"'
            )

        # 2. Les séquences : (table, colonne) -> nom.
        # / 2. Sequences: (table, column) -> name.
        curseur.execute(requete_des_sequences, [NOM_DU_SCHEMA_MODELE])
        sequence_dans_le_modele = {}
        for table, colonne, nom in curseur.fetchall():
            sequence_dans_le_modele[(table, colonne)] = nom

        curseur.execute(requete_des_sequences, [nom_du_schema])
        sequences_du_clone = curseur.fetchall()
        for table, colonne, nom_dans_le_clone in sequences_du_clone:
            nom_attendu = sequence_dans_le_modele.get((table, colonne))
            if nom_attendu is None or nom_attendu == nom_dans_le_clone:
                continue
            curseur.execute(
                f'ALTER SEQUENCE "{nom_du_schema}"."{nom_dans_le_clone}" '
                f'RENAME TO "{nom_attendu}"'
            )


def creer_le_schema_par_clonage(nom_du_schema):
    """
    Crée `nom_du_schema` en copiant le schéma modèle, puis lui donne sa propre clé
    d'empreinte.
    / Creates `nom_du_schema` by copying the template, then gives it its own
    fingerprint key.

    `CloneSchema` (django-tenants) installe puis appelle la fonction SQL
    `public.clone_schema` (pg-clone-schema). Mode "DATA" : tables, index, contraintes,
    séquences (à leur valeur courante) ET lignes. Les lignes du modèle sont celles des
    migrations de données : c'est l'état d'un lieu neuf.
    / CloneSchema installs and calls the public.clone_schema SQL function. "DATA" mode:
    structure, sequences (at their current value) AND rows. The template rows are those
    of the data migrations: the state of a new venue.

    La clé d'empreinte est créée par `LaboutikConfiguration.get_or_create_hmac_key`,
    le même code que pour un lieu dont la clé manque (et la même génération que la
    migration `laboutik 0002`).
    / The key is created by get_or_create_hmac_key, the same code as for a venue
    whose key is missing.
    """
    connection.set_schema_to_public()

    CloneSchema().clone_schema(NOM_DU_SCHEMA_MODELE, nom_du_schema, "DATA")
    reprendre_les_noms_du_modele(nom_du_schema)

    from laboutik.models import LaboutikConfiguration

    with schema_context(nom_du_schema):
        configuration_du_lieu = LaboutikConfiguration.get_solo()
        configuration_du_lieu.get_or_create_hmac_key()

    connection.set_schema_to_public()
