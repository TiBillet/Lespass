"""
Les emplacements vides (`WAITING_CONFIG`) et leurs migrations.
/ Empty slots (WAITING_CONFIG) and their migrations.

LOCALISATION : tests/pytest/test_emplacements_vides_migrations.py

CE QUI EST TESTÉ
- `schema_est_entierement_migre` (Customers/etat_des_migrations.py) : faux pour un
  schéma absent, vide ou à moitié migré ; vrai quand toutes les migrations du code
  sont notées DANS le schéma.
- `cron_morning` : migre chaque emplacement pas à jour ; une migration en échec
  n'arrête ni les suivantes ni le rappel d'adhésion, puis la commande lève une erreur.
- `membership_renewal_reminder` : ignore les emplacements vides ; un lieu en erreur
  n'empêche pas les rappels des lieux suivants.
- `TenantCreateValidator.create_tenant` : un nouveau lieu reçoit le premier
  emplacement entièrement migré, jamais un emplacement à moitié migré.
/ What is tested: the migration check, cron_morning, the reminder, create_tenant.

Chaque test tourne dans une transaction annulée à la fin (`django_db`) : les lignes
`Client` et les schémas créés ici (`CREATE SCHEMA` est transactionnel) disparaissent.
Les emplacements sont créés avec `auto_create_schema = False` : pas de migration.
/ Each test runs in a rolled-back transaction.

Lancer / Run :
docker exec lespass_django poetry run pytest tests/pytest/test_emplacements_vides_migrations.py -q
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import subprocess  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django_tenants.utils import schema_context, tenant_context  # noqa: E402

from Administration.management.commands.cron_morning import Command as CronMorning  # noqa: E402
from BaseBillet.tasks import membership_renewal_reminder  # noqa: E402
from BaseBillet.validators import TenantCreateValidator  # noqa: E402
from Customers.etat_des_migrations import schema_est_entierement_migre  # noqa: E402
from Customers.models import Client  # noqa: E402
from MetaBillet.models import WaitingConfiguration  # noqa: E402


def _creer_un_emplacement_vide(schema_name):
    """
    Une ligne `Client` en `WAITING_CONFIG`, sans schéma PostgreSQL.
    / A WAITING_CONFIG Client row, without a PostgreSQL schema.
    """
    emplacement = Client(
        schema_name=schema_name,
        name=f"Test {schema_name}",
        categorie=Client.WAITING_CONFIG,
    )
    emplacement.auto_create_schema = False
    with schema_context("public"):
        emplacement.save()
    return emplacement


def _creer_un_schema_avec_ses_migrations(schema_name, migrations_notees):
    """
    Un schéma qui ne contient QUE sa table `django_migrations`, remplie avec les
    migrations données. Suffisant pour la vérification, qui ne lit que cette table.
    / A schema holding only its django_migrations table, filled with given rows.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema_name}"')
        cursor.execute(
            f'CREATE TABLE "{schema_name}".django_migrations '
            f"(LIKE public.django_migrations INCLUDING ALL)"
        )
        for app, nom in migrations_notees:
            cursor.execute(
                f'INSERT INTO "{schema_name}".django_migrations (app, name, applied) '
                f"VALUES (%s, %s, now())",
                [app, nom],
            )


def _toutes_les_migrations_du_code():
    """Toutes les migrations connues du code. / Every migration known to the code."""
    return list(MigrationLoader(None, ignore_no_migrations=True).graph.nodes.keys())


# ---------------------------------------------------------------------------
# schema_est_entierement_migre
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_schema_absent_n_est_pas_migre():
    """Un schéma qui n'existe pas n'est pas migré. / A missing schema is not migrated."""
    assert schema_est_entierement_migre("test_emplacement_qui_n_existe_pas") is False


@pytest.mark.django_db
def test_schema_vide_n_est_pas_migre_meme_si_public_l_est():
    """
    Un schéma vide (créé, jamais migré) n'est pas migré. Sa propre table
    `django_migrations` manque : la fonction ne doit pas lire celle de `public` à
    travers le `search_path`.

    On simule une base où Django répondrait « plus rien à jouer » (ce qu'il ferait
    en lisant la table de `public` d'une base à jour). La réponse doit rester
    « pas migré ». Sans cette simulation, le test dépendrait de l'état de `public`
    dans la base de dev.
    / We simulate Django answering "nothing left to apply"; the answer must stay False.
    """
    with connection.cursor() as cursor:
        cursor.execute('CREATE SCHEMA "test_emplacement_schema_vide"')

    with patch(
        "Customers.etat_des_migrations.MigrationExecutor.migration_plan",
        return_value=[],
    ):
        assert schema_est_entierement_migre("test_emplacement_schema_vide") is False


@pytest.mark.django_db
def test_schema_avec_toutes_ses_migrations_est_migre():
    """
    Toutes les migrations du code sont notées dans le schéma : il est à jour.
    / Every code migration is recorded in the schema: up to date.
    """
    _creer_un_schema_avec_ses_migrations(
        "test_emplacement_complet", _toutes_les_migrations_du_code()
    )

    assert schema_est_entierement_migre("test_emplacement_complet") is True


@pytest.mark.django_db
def test_schema_a_moitie_migre_n_est_pas_migre():
    """
    Une seule migration manque (migration interrompue) : le schéma n'est pas à jour.
    / One missing migration (interrupted run): not up to date.
    """
    migrations_sauf_la_derniere = sorted(_toutes_les_migrations_du_code())[:-1]
    _creer_un_schema_avec_ses_migrations(
        "test_emplacement_a_moitie", migrations_sauf_la_derniere
    )

    assert schema_est_entierement_migre("test_emplacement_a_moitie") is False


# ---------------------------------------------------------------------------
# cron_morning
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cron_morning_un_echec_de_migration_n_arrete_pas_les_emplacements_suivants():
    """
    Deux emplacements pas à jour. La migration du premier échoue (simulée) : le second
    est quand même migré, et la commande renvoie le schéma en échec.
    / The first migration fails: the second slot is still migrated.
    """
    _creer_un_emplacement_vide("test_cron_emplacement_en_panne")
    _creer_un_emplacement_vide("test_cron_emplacement_sain")
    emplacements_pas_a_jour = {
        "test_cron_emplacement_en_panne",
        "test_cron_emplacement_sain",
    }

    schemas_migres = []

    def migration_simulee(commande, check):
        schema_name = commande[-1]
        schemas_migres.append(schema_name)
        if schema_name == "test_cron_emplacement_en_panne":
            raise subprocess.CalledProcessError(1, commande)

    with (
        patch(
            "Administration.management.commands.cron_morning.schema_est_entierement_migre",
            side_effect=lambda schema_name: schema_name not in emplacements_pas_a_jour,
        ),
        patch("subprocess.run", side_effect=migration_simulee),
    ):
        schemas_en_echec = CronMorning().migrer_les_emplacements_pas_a_jour()

    assert schemas_migres == [
        "test_cron_emplacement_en_panne",
        "test_cron_emplacement_sain",
    ]
    assert schemas_en_echec == ["test_cron_emplacement_en_panne"]


@pytest.mark.django_db
def test_cron_morning_saute_les_emplacements_deja_a_jour():
    """
    Un emplacement déjà à jour ne relance pas de migration.
    / An up-to-date slot does not run a migration.
    """
    _creer_un_emplacement_vide("test_cron_emplacement_a_jour")

    with (
        patch(
            "Administration.management.commands.cron_morning.schema_est_entierement_migre",
            return_value=True,
        ),
        patch("subprocess.run") as migration_simulee,
    ):
        schemas_en_echec = CronMorning().migrer_les_emplacements_pas_a_jour()

    migration_simulee.assert_not_called()
    assert schemas_en_echec == []


@pytest.mark.django_db
def test_cron_morning_envoie_le_rappel_puis_leve_une_erreur_si_une_migration_echoue():
    """
    Une migration a échoué : le rappel d'adhésion part quand même, puis la commande
    lève une erreur qui nomme le schéma (la tâche Celery est notée en échec).
    / A migration failed: the reminder is still sent, then the command raises.
    """
    commande = CronMorning()
    rappel_simule = MagicMock()

    with (
        patch.object(commande, "create_waiting_tenant", return_value=[]),
        patch.object(
            commande,
            "migrer_les_emplacements_pas_a_jour",
            return_value=["test_schema_en_panne"],
        ),
        patch(
            "Administration.management.commands.cron_morning.membership_renewal_reminder",
            rappel_simule,
        ),
    ):
        with pytest.raises(Exception, match="test_schema_en_panne"):
            commande.handle()

    rappel_simule.delay.assert_called_once()


# ---------------------------------------------------------------------------
# membership_renewal_reminder
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rappel_d_adhesion_ignore_les_emplacements_vides(caplog):
    """
    Un emplacement vide sans schéma ne fait pas planter le rappel : il est ignoré.
    / An empty slot without schema is skipped by the reminder.
    """
    _creer_un_emplacement_vide("test_rappel_emplacement_vide")

    with patch("BaseBillet.tasks.CeleryMailerClass"):
        with caplog.at_level("ERROR", logger="BaseBillet.tasks"):
            membership_renewal_reminder()

    assert "test_rappel_emplacement_vide" not in caplog.text


@pytest.mark.django_db
def test_rappel_d_adhesion_un_lieu_en_erreur_n_empeche_pas_les_suivants(caplog):
    """
    Le premier lieu plante (simulé) : l'erreur est journalisée avec son schéma, et
    les lieux suivants sont quand même traités.
    / The first venue fails: it is logged and the next venues are still processed.
    """
    lieux_attendus = list(
        Client.objects.exclude(schema_name="public")
        .exclude(categorie=Client.WAITING_CONFIG)
        .values_list("schema_name", flat=True)
    )
    assert len(lieux_attendus) >= 2, "Il faut au moins deux lieux en base de dev."

    lieux_traites = []

    def tenant_context_en_panne_pour_le_premier_lieu(tenant):
        lieux_traites.append(tenant.schema_name)
        if len(lieux_traites) == 1:
            raise RuntimeError("panne simulée")
        return tenant_context(tenant)

    with (
        patch(
            "BaseBillet.tasks.tenant_context",
            side_effect=tenant_context_en_panne_pour_le_premier_lieu,
        ),
        patch("BaseBillet.tasks.CeleryMailerClass"),
    ):
        with caplog.at_level("ERROR", logger="BaseBillet.tasks"):
            membership_renewal_reminder()

    assert sorted(lieux_traites) == sorted(lieux_attendus)
    assert lieux_traites[0] in caplog.text


# ---------------------------------------------------------------------------
# create_tenant
# ---------------------------------------------------------------------------


class _ArretApresLeChoixDeLEmplacement(Exception):
    """Arrête create_tenant juste après le choix. / Stops create_tenant after the pick."""


def _brouillon_de_lieu():
    """
    Un brouillon NON enregistré : create_tenant s'arrête avant de l'enregistrer.
    / An unsaved draft: create_tenant stops before saving it.
    """
    return WaitingConfiguration(
        organisation="Test lieu emplacement migre",
        email="test-emplacement-migre@example.com",
        dns_choice="tibillet.localhost",
    )


@pytest.mark.django_db
def test_create_tenant_saute_l_emplacement_a_moitie_migre():
    """
    Le premier emplacement est à moitié migré, le second est complet : le nouveau lieu
    reçoit le second. On arrête create_tenant juste après le choix (création du
    domaine simulée en panne) ; le choix se lit dans la catégorie des emplacements.
    / The half-migrated slot is skipped, the complete one is taken.
    """
    emplacement_a_moitie = _creer_un_emplacement_vide(
        "test_create_emplacement_a_moitie"
    )
    emplacement_complet = _creer_un_emplacement_vide("test_create_emplacement_complet")

    with (
        patch(
            "BaseBillet.validators.schema_est_entierement_migre",
            side_effect=lambda schema_name: (
                schema_name == "test_create_emplacement_complet"
            ),
        ),
        patch(
            "BaseBillet.validators.Domain.objects.get_or_create",
            side_effect=_ArretApresLeChoixDeLEmplacement,
        ),
    ):
        with pytest.raises(_ArretApresLeChoixDeLEmplacement):
            TenantCreateValidator.create_tenant(_brouillon_de_lieu())

    emplacement_a_moitie.refresh_from_db()
    emplacement_complet.refresh_from_db()
    assert emplacement_a_moitie.categorie == Client.WAITING_CONFIG
    assert emplacement_complet.categorie == Client.SALLE_SPECTACLE


@pytest.mark.django_db
def test_create_tenant_refuse_si_aucun_emplacement_n_est_entierement_migre():
    """
    Aucun emplacement n'est complet : create_tenant lève une erreur claire et ne
    touche à aucun emplacement.
    / No complete slot: create_tenant raises and changes no slot.
    """
    emplacement_a_moitie = _creer_un_emplacement_vide("test_create_seul_a_moitie")

    with patch(
        "BaseBillet.validators.schema_est_entierement_migre",
        return_value=False,
    ):
        with pytest.raises(Exception, match="No fully migrated waiting tenant"):
            TenantCreateValidator.create_tenant(_brouillon_de_lieu())

    emplacement_a_moitie.refresh_from_db()
    assert emplacement_a_moitie.categorie == Client.WAITING_CONFIG
