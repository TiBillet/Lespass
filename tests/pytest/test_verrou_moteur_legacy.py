"""
Le verrou de moteur : chaque lieu dit s'il utilise l'ancien Fedow (legacy) ou le moteur V2.
/ The engine lock: each venue says whether it uses the old Fedow (legacy) or the V2 engine.

LOCALISATION : tests/pytest/test_verrou_moteur_legacy.py

RÈGLE MÉTIER TESTÉE (1re partie : le champ, les migrations, la démo)
Spec : TECH_DOC/SESSIONS/FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md §3, §4 et §7,
brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/15-1.md.
- `Client.moteur_monnaie` vaut `legacy` (ancien Fedow) ou `v2` (moteur fedow_core).
  Un `Client` neuf est `v2`.
- La migration `Customers 0006` met tous les lieux existants en `legacy`, sauf les
  emplacements vides du pool (`WAITING_CONFIG`), qui deviendront des lieux neufs : `v2`.
- La migration `BaseBillet 0227` passe en `v2` le lieu dont la `Configuration` a déjà un
  module V2 allumé (caisse, monnaie locale, kiosk, tireuse). Sans `Configuration`, elle ne
  fait rien. Rejouée, elle ne change rien. Elle n'imprime une ligne que pour un lieu
  vraiment basculé : un schéma sans ligne `Client` n'imprime rien.
- `lieu_en_moteur_legacy()` lit `connection.tenant`. Un tenant sans moteur lisible
  (`FakeTenant`, schéma public, `None`) est traité comme legacy : le verrou reste fermé.
- La démo choisit le moteur d'un lieu par son drapeau `caisse_v1_legacy`, jamais par son nom.
/ Business rules: the field and its default, the two migrations, the reader function,
the demo choice by flag.

RÈGLE MÉTIER TESTÉE (2e partie : le verrou côté serveur, tests 8 à 15)
Spec §5.1, §5.3, §5.4, §5.6, §5.7, brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/15-2.md.
- `module_toggle` : un lieu legacy ne peut pas ALLUMER un module V2 (caisse, monnaie
  locale, kiosk, tireuse). Il peut toujours ÉTEINDRE un module V2 resté allumé en base
  (décision Q2). Un lieu v2 bascule ses modules comme avant.
- L'admin `fedow_core` (assets, tokens, transactions, fédérations) et ses routes
  personnalisées (accepter une invitation, exclure un membre) sont fermés à un lieu legacy.
- Un lieu legacy n'est jamais proposé ni accepté dans une invitation V2
  (`pending_invitations` d'un asset, `pending_tenants` d'une fédération, autocomplétion).
- Les points d'entrée V2 (caisse V2, kiosk, tireuse) refusent un lieu legacy.
- « Mon compte » n'ajoute pas les tokens `fedow_core` locaux pour un lieu legacy.
- `api/inventaire/` (`HasLaBoutikAccess`, aucun argent) reste ouvert.
/ Business rules (part 2): the server-side lock.

RÈGLE MÉTIER TESTÉE (3e partie : l'affichage du verrou, tests 16 à 22)
Spec §5.2, §5.5 (réécrite le 2026-10-06, décision Q1), §6, brief
TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/15-3.md.
- Tableau de bord : pour un lieu legacy, les cartes des 4 modules V2 (caisse, monnaie
  locale, kiosk, tireuse) sont fermées (`carte["moteur_legacy"]`, la phrase du verrou, pas
  d'interrupteur). La carte caisse d'un lieu LaBoutik V1 garde son état `v1_active`.
  Un module V2 resté allumé en base garde un interrupteur, pour l'éteindre (décision Q2).
  La carte tireuse n'a pas de lien « Open kiosk ». Les cartes fermées ne comptent pas
  parmi les modules éteints « à découvrir ».
- Menu latéral : les sections des modules V2 (caisse, terminaux, inventaire, tireuse,
  kiosk) exigent un lieu v2. La section « Monnaies » (slug `monnaies`) suit le moteur :
  v2 = les pages `fedow_core`, plus « Assets legacy » si le lieu a des assets legacy ;
  legacy = seulement « Assets legacy », si `module_federation` est allumé ou si le lieu a
  des assets legacy. « Assets » sort du module Fédération. Une page = une section.
/ Business rules (part 3): the lock on the dashboard cards and in the sidebar.

RÈGLE MÉTIER TESTÉE (4e partie : corrections de la relecture, tests 23 à 29)
Brief TECH_DOC/SESSIONS/FEDOW_IMPORT/briefs/15-bis.md, suivi §5 (I1, M7).
- Un lieu v2 ne peut pas appairer une caisse LaBoutik V1 (`Onboard_laboutik`) : refus,
  rien d'écrit. Un lieu legacy appaire comme avant.
- Toute la suite démarre par une vérification légère et automatique : aucun `Client`
  `test_*` en legacy, `lespass` en v2. Au plus une requête sur la table des lieux. Un état
  faux fait échouer, avec la consigne.
- Le schéma public est toujours fermé, quelle que soit la valeur de sa ligne `Client`.
- Une carte fermée par le verrou n'a pas d'encart BETA.
- Le total d'un domaine du tableau de bord compte toutes les cartes réelles ; seule la
  pastille « Découvrir » écarte les cartes fermées et éteintes.
- Les assets legacy du lieu ne sont lus qu'une fois par requête HTTP.
- Un lieu legacy ne supprime pas de fédération V2 ; `AssetAdmin.save_related` retire un
  lieu legacy arrivé dans `pending_invitations`.
- (session « ter », relecture Fable M-1) Une monnaie `fedow_core` archivée n'est plus
  proposée dans le panneau des invitations, et son acceptation est refusée.
/ Business rules (part 4): review fixes.

CONTRAT SUPPOSÉ (ce que ces tests attendent du code)
- `Customers.models.Client.moteur_monnaie`, constantes `Client.MOTEUR_LEGACY = "legacy"` et
  `Client.MOTEUR_V2 = "v2"`, défaut `v2` ;
- `Customers.models.lieu_en_moteur_legacy()` : sans argument, rend `True` (fermé) ou
  `False` (ouvert) ;
- `Customers/migrations/0006_moteur_de_monnaie.py` : trois opérations dans l'ordre
  AddField (défaut `legacy`), RunPython `passer_en_v2_les_emplacements_en_attente`,
  AlterField (défaut `v2`) ;
- `BaseBillet/migrations/0227_moteur_v2_si_un_module_v2_est_actif.py` : RunPython
  `passer_en_v2_si_un_module_v2_est_actif(apps, schema_editor)`, qui lit les modèles par
  `apps.get_model(...)` et le schéma courant par `connection.schema_name` ;
- `Administration/management/commands/demo_data_v2.py` : fonction de module
  `moteur_de_monnaie_du_lieu_de_demo(fixture_du_lieu)`, qui rend `legacy` ou `v2`.
- (3e partie) `Administration/admin/dashboard.py` : chaque carte fermée par le verrou
  porte `carte["moteur_legacy"] = True` ; le gabarit
  `admin/partials/dashboard_module_card.html` affiche alors
  `MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY` (`Customers/models.py`) ; l'élément
  de menu des assets legacy pointe vers
  `staff_admin:fedow_public_assetfedowpublic_changelist` et son titre contient « legacy ».
- (4e partie) `Onboard_laboutik` refuse un lieu v2 par une réponse 409
  `{"detail": ..., "code": "lieu_en_moteur_v2"}`, comme ses autres refus ;
  `tests/outils_moteur_de_monnaie.py` : fonction `verifier_le_depart_de_la_suite()`
  (une requête, `pytest.fail` avec la consigne `down -v`) ; `tests/pytest/conftest.py` :
  fixture autouse de portée session `_moteurs_verifies_au_depart_de_la_suite`.
/ Assumed contract: names of the field, the reader, the migration functions, the demo
function, the closed-card flag and the legacy assets menu entry.

SIMULATIONS
- Aucun `Client` n'est enregistré par ce fichier (un `Client` crée un schéma : ~55 s, et
  le schéma reste). Le défaut se lit sur `Client()` en mémoire.
- Les tests qui écrivent un `Client` ou une `Configuration` tournent dans le lieu dédié
  `test_verrou_moteur_legacy` (`FastTenantTestCase`, schéma cloné). Chaque test y tourne
  dans une transaction annulée à la fin. Ils n'écrivent jamais dans `lespass` ni dans un
  lieu de démo.
- La `Configuration` du lieu dédié est modifiée par `update()` (ou créée par
  `bulk_create()` si elle manque), jamais par `save()` : `save()` écrirait le singleton
  dans memcached, que le rollback n'annule pas (tests/PIEGES.md 13.5, 13.22). La migration
  relit la base (`objects.first()`) : elle voit la valeur posée.
/ No Client is saved. Writes happen in a dedicated test venue, in a rolled-back
transaction, through update()/bulk_create() only (no cache write).

Lancer / Run : make test ARGS="tests/pytest/test_verrou_moteur_legacy.py"
"""

import contextlib
import importlib
import io
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.apps import apps as registre_des_applications
from django.contrib import messages as messages_django
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied as PermissionDeniedDjango
from django.core.exceptions import ValidationError
from django.db import connection, migrations, transaction
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import translation
from django.utils.html import escape
from django_tenants.test.cases import FastTenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context, tenant_context
from rest_framework.exceptions import PermissionDenied as PermissionDeniedDrf

import fedow_core.admin  # noqa: F401  (enregistre les admins fedow_core / registers them)
from Administration.admin import dashboard
from Administration.admin_tenant import staff_admin_site
from ApiBillet.views import Onboard_laboutik
from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import Configuration
from BaseBillet.permissions import HasLaBoutikAccess, HasLaBoutikTerminalAccess
from BaseBillet.views import MyAccount, get_distant_fedow_tokens
from controlvanne.permissions import HasTireuseAccess
from Customers.models import MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY, Client
from fedow_core.models import Asset, Federation, Token
from fedow_public.models import AssetFedowPublic
from inventaire.views import DebitMetreViewSet, StockViewSet
from kiosk.views import IsKioskTerminal

# Les deux valeurs du moteur, telles que la spec les fixe (§3).
# Écrites en texte : le test les lit même quand les constantes du modèle n'existent pas.
# / The two engine values, as fixed by the spec.
MOTEUR_LEGACY = "legacy"
MOTEUR_V2 = "v2"

# Les modules de la Configuration qui font d'un lieu un lieu V2 (spec §4.2).
# / The Configuration modules that make a venue a V2 venue.
DRAPEAUX_DES_MODULES_V2 = [
    "module_caisse",
    "module_monnaie_locale",
    "module_kiosk",
    "module_tireuse",
]

# Des modules qui ne sont PAS des modules V2 : allumés seuls, le lieu reste legacy.
# `module_inventaire` (stock des articles) n'est pas monétaire (spec §5.1).
# / Modules that are NOT V2 modules: alone, the venue stays legacy.
DRAPEAUX_DES_MODULES_QUI_NE_SONT_PAS_V2 = [
    "module_billetterie",
    "module_adhesion",
    "module_federation",
    "module_inventaire",
]

# Les modules des migrations (leur nom commence par un chiffre : import par leur chemin).
# / The migration modules (their name starts with a digit: imported by their path).
CHEMIN_DE_LA_MIGRATION_CUSTOMERS_0006 = "Customers.migrations.0006_moteur_de_monnaie"
CHEMIN_DE_LA_MIGRATION_BASEBILLET_0227 = (
    "BaseBillet.migrations.0227_moteur_v2_si_un_module_v2_est_actif"
)
CHEMIN_DE_LA_COMMANDE_DE_DEMO = "Administration.management.commands.demo_data_v2"


def fonction_de_la_migration_0227():
    """La fonction RunPython de `BaseBillet 0227`.
    / The RunPython function of BaseBillet 0227."""
    module_de_la_migration = importlib.import_module(
        CHEMIN_DE_LA_MIGRATION_BASEBILLET_0227
    )
    return module_de_la_migration.passer_en_v2_si_un_module_v2_est_actif


def lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(apps_de_la_migration):
    """
    Appelle la fonction de `0227` comme `migrate` l'appelle, et rend le texte imprimé.
    Le `schema_editor` porte la connexion : la fonction peut lire le schéma par lui ou
    par `django.db.connection`.
    / Calls 0227's function like `migrate` does, and returns what it printed.
    """
    faux_schema_editor = SimpleNamespace(connection=connection)
    texte_imprime = io.StringIO()
    with contextlib.redirect_stdout(texte_imprime):
        fonction_de_la_migration_0227()(apps_de_la_migration, faux_schema_editor)
    return texte_imprime.getvalue()


def lieu_en_moteur_legacy():
    """
    Appelle `Customers.models.lieu_en_moteur_legacy()`. L'import se fait ici : sans la
    fonction, seul le test qui l'appelle échoue, pas tout le fichier.
    / Calls the reader; imported here so a missing function fails only its test.
    """
    module_des_modeles_customers = importlib.import_module("Customers.models")
    return module_des_modeles_customers.lieu_en_moteur_legacy()


# --------------------------------------------------------------------------
# 1 — Un Client neuf est v2
# / 1 — A new Client is v2
# --------------------------------------------------------------------------


def test_un_client_neuf_est_v2_par_defaut():
    """
    Un `Client` créé après le déploiement démarre sur le moteur V2 (spec §2.2, §3).
    On lit le défaut sur un objet en mémoire : rien n'est enregistré.
    / A Client created after deployment starts on V2; read on an unsaved object.
    """
    client_en_memoire = Client()

    assert client_en_memoire.moteur_monnaie == MOTEUR_V2
    assert Client.MOTEUR_LEGACY == MOTEUR_LEGACY
    assert Client.MOTEUR_V2 == MOTEUR_V2


# --------------------------------------------------------------------------
# 6 — lieu_en_moteur_legacy() : sans moteur lisible, le verrou reste fermé
# / 6 — lieu_en_moteur_legacy(): without a readable engine, the lock stays closed
# --------------------------------------------------------------------------


def test_lieu_en_moteur_legacy_none_vaut_ferme():
    """
    `lieu_en_moteur_legacy()` lit `connection.tenant` :
    - `FakeTenant` d'un lieu (posé par `schema_context`) → fermé (True) ;
    - `FakeTenant` du schéma public → fermé (True) ;
    - `None` → fermé (True) ;
    - un `Client` legacy → fermé (True) ;
    - un `Client` v2 → ouvert (False).
    Les `Client` sont en mémoire, jamais enregistrés. `tenant_context` remet le tenant
    d'avant en sortant.
    / FakeTenant, public schema and None are closed; legacy closed; v2 open.
    """
    with schema_context("lespass"):
        assert lieu_en_moteur_legacy() is True

    with schema_context(get_public_schema_name()):
        assert lieu_en_moteur_legacy() is True

    tenant_avant_le_test = connection.tenant
    try:
        connection.tenant = None
        assert lieu_en_moteur_legacy() is True
    finally:
        connection.tenant = tenant_avant_le_test

    lieu_legacy_en_memoire = Client(schema_name="lespass", moteur_monnaie=MOTEUR_LEGACY)
    with tenant_context(lieu_legacy_en_memoire):
        assert lieu_en_moteur_legacy() is True

    lieu_v2_en_memoire = Client(schema_name="lespass", moteur_monnaie=MOTEUR_V2)
    with tenant_context(lieu_v2_en_memoire):
        assert lieu_en_moteur_legacy() is False


# --------------------------------------------------------------------------
# 7 — La démo choisit le moteur par le drapeau caisse_v1_legacy
# / 7 — The demo picks the engine by the caisse_v1_legacy flag
# --------------------------------------------------------------------------


def test_demo_lieu_legacy_par_le_drapeau_caisse_v1_legacy():
    """
    La fonction de la démo qui choisit le moteur d'un lieu suit le drapeau
    `caisse_v1_legacy` de sa fixture, jamais son nom (décision Q6 du suivi).
    - drapeau vrai → legacy, quel que soit le nom ;
    - pas de drapeau → v2, même pour le nom « Festival ».
    Appel direct : la démo n'est pas relancée.
    / The demo function follows the flag, never the name.
    """
    module_de_la_demo = importlib.import_module(CHEMIN_DE_LA_COMMANDE_DE_DEMO)
    moteur_de_monnaie_du_lieu_de_demo = (
        module_de_la_demo.moteur_de_monnaie_du_lieu_de_demo
    )

    assert (
        moteur_de_monnaie_du_lieu_de_demo(
            {"name": "Festival", "caisse_v1_legacy": True}
        )
        == MOTEUR_LEGACY
    )
    assert (
        moteur_de_monnaie_du_lieu_de_demo(
            {"name": "Un lieu au nom quelconque", "caisse_v1_legacy": True}
        )
        == MOTEUR_LEGACY
    )
    assert moteur_de_monnaie_du_lieu_de_demo({"name": "Festival"}) == MOTEUR_V2
    assert (
        moteur_de_monnaie_du_lieu_de_demo(
            {"name": "Festival", "caisse_v1_legacy": False}
        )
        == MOTEUR_V2
    )
    assert moteur_de_monnaie_du_lieu_de_demo({"name": "Lespass"}) == MOTEUR_V2


# --------------------------------------------------------------------------
# 25 — Le schéma public est toujours fermé (M1)
# / 25 — The public schema is always closed (M1)
# --------------------------------------------------------------------------


def test_schema_public_toujours_ferme():
    """
    Le schéma public n'est pas un lieu : il est toujours fermé, quelle que soit la valeur
    de sa ligne `Client`. Sur une base neuve, cette ligne est créée après la migration
    `Customers 0006`, donc en `v2` : la fonction ne doit pas la croire.
    `Client` en mémoire, jamais enregistré ; `tenant_context` remet le tenant d'avant.
    / The public schema is always closed, whatever its Client row says.
    """
    schema_public_en_v2_en_memoire = Client(
        schema_name=get_public_schema_name(), moteur_monnaie=MOTEUR_V2
    )
    with tenant_context(schema_public_en_v2_en_memoire):
        assert lieu_en_moteur_legacy() is True


# --------------------------------------------------------------------------
# 24 (2/2) — La vérification de départ s'applique à toute la suite (I2)
# / 24 (2/2) — The start-up check applies to the whole suite (I2)
# --------------------------------------------------------------------------


def test_verification_de_depart_automatique_appliquee_a_toute_la_suite(request):
    """
    La vérification de départ légère est une fixture `autouse` du conftest pytest : elle
    s'applique à chaque test sans qu'il la demande. On le lit dans les fixtures actives de
    CE test, qui ne la demande pas. Son comportement est testé dans
    `TestVerrouDuMoteurCoteServeur.test_verification_de_depart_automatique`.
    / The light start-up check is an autouse fixture: active for a test that never asks.
    """
    assert "_moteurs_verifies_au_depart_de_la_suite" in request.fixturenames


# --------------------------------------------------------------------------
# 2 à 5 — Les migrations, dans un lieu dédié
# / 2 to 5 — The migrations, in a dedicated venue
# --------------------------------------------------------------------------


class TestMigrationsDuMoteurDeMonnaie(FastTenantTestCase):
    """
    Les deux migrations du moteur, appelées directement dans le lieu dédié
    `test_verrou_moteur_legacy`. Chaque test tourne dans une transaction annulée à la fin.
    / The two engine migrations, called directly in the dedicated venue; rolled back.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_verrou_moteur_legacy"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-verrou-moteur-legacy.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test verrou moteur legacy"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)

    # ------------------------------------------------------------------ #
    #  Outils / Helpers                                                   #
    # ------------------------------------------------------------------ #

    def poser_le_moteur_du_lieu_dedie(self, moteur):
        """Pose le moteur du lieu dédié en base, par `update()`.
        / Sets the dedicated venue's engine in the database."""
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=moteur)

    def moteur_du_lieu_dedie_lu_en_base(self):
        """Le moteur du lieu dédié, relu en base. / Engine read back from the database."""
        return (
            Client.objects.filter(pk=self.tenant.pk)
            .values_list("moteur_monnaie", flat=True)
            .get()
        )

    def poser_les_drapeaux_de_la_configuration(self, drapeaux_allumes):
        """
        Éteint tous les modules cités par ce fichier, puis allume ceux de la liste.
        Crée la ligne du singleton par `bulk_create()` si elle manque (un schéma cloné
        n'en a pas). Jamais de `save()` : il écrirait le singleton dans memcached.
        / Turns off every module named in this file, then turns on the listed ones.
        """
        if Configuration.objects.first() is None:
            Configuration.objects.bulk_create(
                [
                    Configuration(
                        pk=Configuration.singleton_instance_id,
                        organisation="Test verrou moteur legacy",
                        slug="test-verrou-moteur-legacy",
                    )
                ]
            )

        valeurs_des_drapeaux = {}
        for nom_du_drapeau in DRAPEAUX_DES_MODULES_V2:
            valeurs_des_drapeaux[nom_du_drapeau] = False
        for nom_du_drapeau in DRAPEAUX_DES_MODULES_QUI_NE_SONT_PAS_V2:
            valeurs_des_drapeaux[nom_du_drapeau] = False
        for nom_du_drapeau in drapeaux_allumes:
            valeurs_des_drapeaux[nom_du_drapeau] = True

        Configuration.objects.update(**valeurs_des_drapeaux)

    # ------------------------------------------------------------------ #
    #  2 — Customers 0006                                                 #
    # ------------------------------------------------------------------ #

    def test_migration_0006_met_les_lieux_existants_en_legacy(self):
        """
        `Customers 0006`, comme la spec la décrit (§4.1) :
        - trois opérations dans l'ordre : AddField (défaut `legacy` : toutes les lignes
          existantes deviennent legacy), RunPython, AlterField (défaut `v2`) ;
        - la fonction RunPython passe en `v2` les `Client` `WAITING_CONFIG`, et laisse
          `legacy` un lieu d'une autre catégorie ;
        - le retour arrière ne fait rien.
        La fonction est appelée dans le schéma public, comme `migrate_schemas` le fait pour
        une app partagée. Le lieu dédié sert de ligne `Client` à modifier.
        / Three operations in order; WAITING_CONFIG goes v2, other categories stay legacy.
        """
        module_de_la_migration = importlib.import_module(
            CHEMIN_DE_LA_MIGRATION_CUSTOMERS_0006
        )
        operations_de_la_migration = module_de_la_migration.Migration.operations

        assert len(operations_de_la_migration) == 3
        ajout_du_champ, passage_en_v2, changement_du_defaut = operations_de_la_migration

        assert isinstance(ajout_du_champ, migrations.AddField)
        assert ajout_du_champ.model_name == "client"
        assert ajout_du_champ.name == "moteur_monnaie"
        assert ajout_du_champ.field.default == MOTEUR_LEGACY

        assert isinstance(passage_en_v2, migrations.RunPython)
        fonction_de_passage_en_v2 = (
            module_de_la_migration.passer_en_v2_les_emplacements_en_attente
        )
        assert passage_en_v2.code is fonction_de_passage_en_v2
        assert passage_en_v2.reverse_code is migrations.RunPython.noop

        assert isinstance(changement_du_defaut, migrations.AlterField)
        assert changement_du_defaut.model_name == "client"
        assert changement_du_defaut.name == "moteur_monnaie"
        assert changement_du_defaut.field.default == MOTEUR_V2

        # Un lieu d'une autre catégorie reste legacy.
        # / A venue of another category stays legacy.
        Client.objects.filter(pk=self.tenant.pk).update(
            categorie=Client.SALLE_SPECTACLE, moteur_monnaie=MOTEUR_LEGACY
        )
        connection.set_schema_to_public()
        fonction_de_passage_en_v2(registre_des_applications, None)
        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_LEGACY

        # Un emplacement vide du pool passe en v2.
        # / An empty pool slot goes v2.
        Client.objects.filter(pk=self.tenant.pk).update(
            categorie=Client.WAITING_CONFIG, moteur_monnaie=MOTEUR_LEGACY
        )
        fonction_de_passage_en_v2(registre_des_applications, None)
        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_V2

    # ------------------------------------------------------------------ #
    #  3 — BaseBillet 0227 : un module V2 allumé passe le lieu en v2      #
    # ------------------------------------------------------------------ #

    def test_migration_0227_depend_de_customers_0006_et_de_basebillet_0226(self):
        """
        `0227` tourne dans chaque lieu après `Customers 0006` (le champ existe) et après
        la dernière migration de BaseBillet (spec §4.2).
        / 0227 depends on Customers 0006 and BaseBillet 0226.
        """
        module_de_la_migration = importlib.import_module(
            CHEMIN_DE_LA_MIGRATION_BASEBILLET_0227
        )
        dependances = module_de_la_migration.Migration.dependencies

        assert ("Customers", "0006_moteur_de_monnaie") in dependances
        assert (
            "BaseBillet",
            "0226_retirer_le_skin_de_la_configuration",
        ) in dependances

    def test_migration_0227_passe_en_v2_un_lieu_avec_un_module_v2(self):
        """
        Pour chacun des quatre modules V2, allumé seul : le lieu legacy passe en `v2`, et
        la migration imprime une ligne qui nomme le schéma.
        / For each of the four V2 modules, alone: the venue goes v2 and a line is printed.
        """
        for nom_du_drapeau in DRAPEAUX_DES_MODULES_V2:
            self.poser_les_drapeaux_de_la_configuration([nom_du_drapeau])
            self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

            texte_imprime = lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(
                registre_des_applications
            )

            assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_V2, nom_du_drapeau
            assert self.get_test_schema_name() in texte_imprime, nom_du_drapeau
            assert MOTEUR_V2 in texte_imprime, nom_du_drapeau

    def test_migration_0227_laisse_en_legacy_un_lieu_sans_module_v2(self):
        """
        Aucun module V2 allumé (mais billetterie, adhésion, fédération et inventaire
        allumés) : le lieu reste `legacy`, et rien n'est imprimé.
        / No V2 module on (other modules on): the venue stays legacy, nothing printed.
        """
        self.poser_les_drapeaux_de_la_configuration(
            DRAPEAUX_DES_MODULES_QUI_NE_SONT_PAS_V2
        )
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        texte_imprime = lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(
            registre_des_applications
        )

        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_LEGACY
        assert texte_imprime == ""

    # ------------------------------------------------------------------ #
    #  4 — BaseBillet 0227 : un schéma sans Configuration                 #
    # ------------------------------------------------------------------ #

    def test_migration_0227_sans_configuration_ne_fait_rien(self):
        """
        Un lieu neuf n'a pas encore de `Configuration` quand `0227` tourne. Un faux
        `apps` rend un modèle `Configuration` sans aucune ligne ; le vrai `Client`.
        La fonction rend la main sans erreur : le lieu legacy reste legacy, rien
        n'est imprimé.
        / Fake `apps` with an empty Configuration: no error, nothing changes or prints.
        """
        modele_configuration_sans_ligne = SimpleNamespace(
            objects=Configuration.objects.none()
        )

        def get_model_du_faux_apps(nom_de_l_application, nom_du_modele):
            if (nom_de_l_application, nom_du_modele) == ("BaseBillet", "Configuration"):
                return modele_configuration_sans_ligne
            return registre_des_applications.get_model(
                nom_de_l_application, nom_du_modele
            )

        faux_apps_sans_configuration = SimpleNamespace(get_model=get_model_du_faux_apps)
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        texte_imprime = lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(
            faux_apps_sans_configuration
        )

        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_LEGACY
        assert texte_imprime == ""

    # ------------------------------------------------------------------ #
    #  5 — BaseBillet 0227 : rejouée, et dans un schéma sans Client       #
    # ------------------------------------------------------------------ #

    def test_migration_0227_rejouee_ne_change_rien_et_n_imprime_rien_sans_client(self):
        """
        - Rejouée sur un lieu déjà basculé : le lieu reste `v2`, aucune erreur.
        - Dans un schéma sans ligne `Client` (comme `test_modele`) : la ligne du lieu
          est renommée le temps de la transaction, l'`update()` ne touche aucune ligne,
          rien n'est imprimé.
        / Replayed: still v2. In a schema without a Client row: nothing printed.
        """
        self.poser_les_drapeaux_de_la_configuration(["module_caisse"])
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(registre_des_applications)
        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_V2

        lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(registre_des_applications)
        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_V2

        # Plus aucune ligne Client ne porte le nom du schéma courant.
        # / No Client row carries the current schema name anymore.
        Client.objects.filter(pk=self.tenant.pk).update(
            schema_name="test_verrou_moteur_legacy_ligne_renommee",
            moteur_monnaie=MOTEUR_LEGACY,
        )
        assert not Client.objects.filter(schema_name=connection.schema_name).exists()

        texte_imprime = lancer_la_migration_0227_et_lire_ce_qu_elle_imprime(
            registre_des_applications
        )

        assert texte_imprime == ""
        assert self.moteur_du_lieu_dedie_lu_en_base() == MOTEUR_LEGACY


# ==========================================================================
# 2e PARTIE — LE VERROU CÔTÉ SERVEUR (tests 8 à 15)
# / PART 2 — THE SERVER-SIDE LOCK (tests 8 to 15)
# ==========================================================================


def permission_accordee(permission, requete):
    """
    Rend True si la permission DRF laisse passer la requête, False sinon.
    Une permission peut refuser de deux façons : rendre False, ou lever
    `PermissionDenied` (chemin de la clé API absente). Les deux comptent comme un refus.
    / True if the DRF permission lets the request through; False or PermissionDenied = refused.
    """
    try:
        return bool(permission.has_permission(requete, None))
    except (PermissionDeniedDrf, PermissionDeniedDjango):
        return False


def faux_fedow_distant_injoignable():
    """
    Remplace le client du Fedow distant (`BaseBillet.views.FedowAPI`) par un faux dont
    chaque appel lève une erreur : la vue continue sans tokens distants, comme quand le
    Fedow est en panne. Seuls les tokens locaux (`fedow_core`) peuvent alors apparaître.
    / Remote Fedow client whose every call fails: only local tokens can show up.
    """
    faux_client_fedow = MagicMock()
    erreur_du_fedow = ConnectionError("Fedow distant injoignable (test)")
    faux_client_fedow.wallet.cached_retrieve_by_signature.side_effect = erreur_du_fedow
    faux_client_fedow.NFCcard.retrieve_card_by_signature.side_effect = erreur_du_fedow
    faux_client_fedow.transaction.paginated_list_by_wallet_signature.side_effect = (
        erreur_du_fedow
    )
    return patch("BaseBillet.views.FedowAPI", return_value=faux_client_fedow)


class TestVerrouDuMoteurCoteServeur(FastTenantTestCase):
    """
    Le verrou côté serveur, dans le lieu dédié `test_verrou_moteur_legacy`.
    / The server-side lock, in the dedicated test venue.

    SIMULATIONS
    - Le moteur du lieu est posé en base par `update()` à chaque test (legacy ou v2),
      jamais supposé : la ligne `Client` du lieu dédié peut porter l'une ou l'autre
      valeur au départ. Puis la connexion reçoit le `Client` relu en base : c'est ce que
      le middleware fait à chaque requête HTTP.
    - La `Configuration` lue par `module_toggle` et par les permissions est un objet EN
      MÉMOIRE rendu par `get_solo()` patché ; `save()` est patché aussi. Rien n'est écrit
      dans la base ni dans memcached (tests/PIEGES.md 13.5, 13.22).
    - Le cache du singleton du lieu dédié est vidé au début et à la fin de chaque test :
      une page d'admin ou un signal peut l'avoir rempli avec une ligne annulée ensuite
      (tests/PIEGES.md 9.86).
    - Les utilisateurs, wallets, assets, tokens et fédérations sont créés dans la
      transaction du test, annulée à la fin (tests/PIEGES.md 13.24 : pas de suppression).
    - Le Fedow distant est remplacé par un faux qui échoue : aucun appel réseau.
    / Engine set by update() then re-read; in-memory Configuration with patched
    get_solo()/save(); singleton cache cleared; everything rolled back; no network.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_verrou_moteur_legacy"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-verrou-moteur-legacy.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test verrou moteur legacy"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

        # Un schéma cloné n'a pas de ligne de Configuration : on la crée par
        # `bulk_create()` (jamais `save()`, qui écrirait memcached).
        # / A cloned schema has no Configuration row: bulk_create, never save().
        if Configuration.objects.first() is None:
            Configuration.objects.bulk_create(
                [
                    Configuration(
                        pk=Configuration.singleton_instance_id,
                        organisation="Test verrou moteur legacy",
                        slug="test-verrou-moteur-legacy",
                    )
                ]
            )

        # Un gestionnaire du lieu : admin du lieu, pas superadmin.
        # / A venue manager: tenant admin, not superadmin.
        self.administrateur_du_lieu = self.creer_un_utilisateur(
            prefixe_de_l_email="admin-verrou",
            est_staff=True,
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)

        self.fabrique_de_requetes = RequestFactory()

    def tearDown(self):
        # Une page d'admin ou un signal a pu remplir le cache du singleton avec une ligne
        # que l'annulation va effacer : on le vide.
        # / An admin page or a signal may have cached a row the rollback will erase.
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

    # ------------------------------------------------------------------ #
    #  Outils / Helpers                                                   #
    # ------------------------------------------------------------------ #

    def poser_le_moteur_du_lieu_dedie(self, moteur):
        """
        Pose le moteur du lieu dédié en base par `update()`, puis place la connexion sur
        le `Client` relu en base. Rend ce `Client`.
        / Sets the engine by update(), then puts the re-read Client on the connection.
        """
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=moteur)
        lieu_relu_en_base = Client.objects.get(pk=self.tenant.pk)
        connection.set_tenant(lieu_relu_en_base)
        return lieu_relu_en_base

    def creer_un_utilisateur(self, prefixe_de_l_email, est_staff=False, wallet=None):
        """
        Un utilisateur humain à l'email unique, créé dans la transaction du test.
        / A human user with a unique email, created inside the test transaction.
        """
        email_unique = (
            f"{prefixe_de_l_email}-{uuid.uuid4().hex[:12]}@tibillet.localhost"
        )
        return TibilletUser.objects.create(
            email=email_unique,
            username=email_unique,
            espece=TibilletUser.TYPE_HUM,
            is_staff=est_staff,
            is_active=True,
            wallet=wallet,
        )

    def construire_une_requete(self, methode, chemin, utilisateur, parametres=None):
        """
        Une requête de `RequestFactory`, avec un utilisateur, une session et des messages.
        / A RequestFactory request with a user, a session and message storage.
        """
        if parametres is None:
            parametres = {}
        if methode == "post":
            requete = self.fabrique_de_requetes.post(chemin, data=parametres)
        else:
            requete = self.fabrique_de_requetes.get(chemin, data=parametres)
        requete.user = utilisateur
        SessionMiddleware(lambda requete_recue: None).process_request(requete)
        requete._messages = FallbackStorage(requete)
        return requete

    def navigateur_connecte(self):
        """
        Le client HTTP du lieu dédié, connecté comme gestionnaire. Le middleware relit
        le `Client` en base à chaque requête : il voit le moteur posé par `update()`.
        / HTTP client of the venue, logged in; the middleware re-reads the Client.
        """
        navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        navigateur.force_login(self.administrateur_du_lieu)
        return navigateur

    def configuration_en_memoire(self, modules_v2_allumes, **autres_valeurs):
        """
        Une `Configuration` en mémoire, jamais enregistrée : les quatre modules V2 éteints
        sauf ceux de la liste.
        / An in-memory Configuration, never saved: V2 modules off except the listed ones.
        """
        configuration = Configuration(
            pk=Configuration.singleton_instance_id,
            organisation="Test verrou moteur legacy",
            slug="test-verrou-moteur-legacy",
            **autres_valeurs,
        )
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            setattr(configuration, nom_du_module, nom_du_module in modules_v2_allumes)
        return configuration

    def basculer_un_module(self, nom_du_module, configuration):
        """
        Appelle `ConfigurationAdmin.module_toggle` comme le POST HTMX du tableau de bord.
        `get_solo()` rend la `Configuration` en mémoire, `save()` est un faux qui note
        ses appels. Rend la réponse, le faux `save()` et les niveaux des messages.
        / Calls module_toggle with an in-memory Configuration and a fake save().
        """
        requete = self.construire_une_requete(
            "post",
            f"/admin/BaseBillet/configuration/module-toggle/{nom_du_module}/",
            self.administrateur_du_lieu,
        )
        admin_de_la_configuration = staff_admin_site._registry[Configuration]

        with patch.object(Configuration, "get_solo", return_value=configuration):
            with patch.object(Configuration, "save", autospec=True) as faux_save:
                reponse = admin_de_la_configuration.module_toggle(
                    requete, nom_du_module
                )

        niveaux_des_messages = [message.level for message in requete._messages]
        return reponse, faux_save, niveaux_des_messages

    def drapeaux_des_modules_v2(self, configuration):
        """Les quatre drapeaux V2 de la configuration. / The four V2 flags."""
        valeurs_des_drapeaux = {}
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            valeurs_des_drapeaux[nom_du_module] = getattr(configuration, nom_du_module)
        return valeurs_des_drapeaux

    def creer_un_asset_du_lieu(self, nom, categorie=Asset.FID):
        """
        Un asset `fedow_core` créé par le lieu dédié. Catégorie FID par défaut : le signal
        de création n'ajoute alors aucun produit de recharge.
        / A fedow_core asset created by the venue (FID: no top-up product signal).
        """
        portefeuille_d_origine = Wallet.objects.create(
            name=f"Portefeuille {nom} {uuid.uuid4().hex[:8]}"
        )
        return Asset.objects.create(
            name=f"{nom} {uuid.uuid4().hex[:8]}",
            currency_code="PTS",
            category=categorie,
            tenant_origin=self.tenant,
            wallet_origin=portefeuille_d_origine,
        )

    def creer_une_federation_du_lieu(self, nom):
        """Une fédération V2 créée par le lieu dédié. / A V2 federation created by the venue."""
        federation = Federation.objects.create(
            name=f"{nom} {uuid.uuid4().hex[:8]}",
            created_by=self.tenant,
        )
        federation.tenants.add(self.tenant)
        return federation

    # ------------------------------------------------------------------ #
    #  8 — module_toggle : allumer un module V2 est refusé en legacy      #
    # ------------------------------------------------------------------ #

    def test_module_toggle_refuse_d_allumer_un_module_v2_en_legacy(self):
        """
        Lieu legacy, les quatre modules V2 éteints. Pour chacun : la bascule est refusée
        AVANT toute écriture (spec §5.1) :
        - les quatre drapeaux restent éteints (la caisse n'allume pas non plus la monnaie
          locale) ;
        - `save()` n'est jamais appelé ;
        - un message d'erreur, et la même réponse que les refus existants (200,
          `HX-Refresh`).
        Même refus pour la caisse d'un lieu qui a un serveur LaBoutik V1
        (`server_cashless`) : l'interrupteur caché ne suffit pas, le POST direct est refusé.
        / Legacy venue: switching ON any V2 module is refused before any write.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        cas_a_verifier = []
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            cas_a_verifier.append((nom_du_module, self.configuration_en_memoire([])))
        cas_a_verifier.append(
            (
                "module_caisse",
                self.configuration_en_memoire(
                    [], server_cashless="https://laboutik-v1.example.org"
                ),
            )
        )

        tous_eteints = {}
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            tous_eteints[nom_du_module] = False

        for nom_du_module, configuration in cas_a_verifier:
            reponse, faux_save, niveaux_des_messages = self.basculer_un_module(
                nom_du_module, configuration
            )
            contexte = (
                f"{nom_du_module} (server_cashless={configuration.server_cashless!r})"
            )

            assert self.drapeaux_des_modules_v2(configuration) == tous_eteints, contexte
            assert faux_save.call_count == 0, contexte
            assert messages_django.ERROR in niveaux_des_messages, contexte
            assert reponse.status_code == 200, contexte
            assert reponse["HX-Refresh"] == "true", contexte

    # ------------------------------------------------------------------ #
    #  9 — module_toggle : éteindre un module V2 reste permis en legacy   #
    # ------------------------------------------------------------------ #

    def test_module_toggle_permet_d_eteindre_un_module_v2_en_legacy(self):
        """
        Lieu legacy dont les quatre modules V2 sont restés allumés en base. Il peut les
        éteindre (décision Q2 : « interrupteur visible seulement pour éteindre »).

        L'ordre des gardes, décrit ici :
        - le verrou legacy ne refuse QUE l'allumage ; une extinction passe à la suite ;
        - la règle existante « la caisse exige la monnaie locale » s'applique ensuite,
          inchangée : éteindre la monnaie locale tant que la caisse est allumée est
          refusé par CETTE règle (message d'erreur, drapeau remis), pas par le verrou.
          La spec (§5.1) ne demande pas de la lever pour un lieu legacy ;
        - le chemin pour tout éteindre : la caisse d'abord, puis la monnaie locale ;
          kiosk et tireuse s'éteignent seuls.
        / Legacy venue with V2 modules still on: it can switch them off; the existing
        "POS requires local currency" rule still applies (POS first, then currency).
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        configuration = self.configuration_en_memoire(DRAPEAUX_DES_MODULES_V2)

        # La monnaie locale tant que la caisse est allumée : règle existante.
        # / Local currency while the POS is on: existing rule.
        _reponse, _faux_save, niveaux_des_messages = self.basculer_un_module(
            "module_monnaie_locale", configuration
        )
        assert configuration.module_monnaie_locale is True
        assert configuration.module_caisse is True
        assert messages_django.ERROR in niveaux_des_messages

        # La caisse, puis la monnaie locale, puis le kiosk, puis la tireuse : tout passe.
        # / POS, then local currency, then kiosk, then tap: all go through.
        ordre_d_extinction = [
            "module_caisse",
            "module_monnaie_locale",
            "module_kiosk",
            "module_tireuse",
        ]
        for nom_du_module in ordre_d_extinction:
            reponse, faux_save, niveaux_des_messages = self.basculer_un_module(
                nom_du_module, configuration
            )

            assert getattr(configuration, nom_du_module) is False, nom_du_module
            assert faux_save.call_count == 1, nom_du_module
            assert messages_django.ERROR not in niveaux_des_messages, nom_du_module
            assert reponse["HX-Refresh"] == "true", nom_du_module

        tous_eteints = {}
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            tous_eteints[nom_du_module] = False
        assert self.drapeaux_des_modules_v2(configuration) == tous_eteints

    # ------------------------------------------------------------------ #
    #  10 — module_toggle : un lieu v2 bascule comme avant                #
    # ------------------------------------------------------------------ #

    def test_module_toggle_v2_inchange(self):
        """
        Lieu v2 (non-régression) :
        - le kiosk et la tireuse s'allument ;
        - la caisse s'allume et allume la monnaie locale avec elle ;
        - éteindre la monnaie locale tant que la caisse est allumée est refusé (règle
          existante) ;
        - la caisse, puis la monnaie locale, le kiosk et la tireuse s'éteignent.
        / V2 venue: modules switch on and off as before.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration = self.configuration_en_memoire([])

        for nom_du_module in ["module_kiosk", "module_tireuse"]:
            _reponse, faux_save, niveaux_des_messages = self.basculer_un_module(
                nom_du_module, configuration
            )
            assert getattr(configuration, nom_du_module) is True, nom_du_module
            assert faux_save.call_count == 1, nom_du_module
            assert messages_django.ERROR not in niveaux_des_messages, nom_du_module

        _reponse, faux_save, niveaux_des_messages = self.basculer_un_module(
            "module_caisse", configuration
        )
        assert configuration.module_caisse is True
        assert configuration.module_monnaie_locale is True
        assert faux_save.call_count == 1
        assert messages_django.ERROR not in niveaux_des_messages

        _reponse, _faux_save, niveaux_des_messages = self.basculer_un_module(
            "module_monnaie_locale", configuration
        )
        assert configuration.module_monnaie_locale is True
        assert messages_django.ERROR in niveaux_des_messages

        for nom_du_module in [
            "module_caisse",
            "module_monnaie_locale",
            "module_kiosk",
            "module_tireuse",
        ]:
            _reponse, faux_save, niveaux_des_messages = self.basculer_un_module(
                nom_du_module, configuration
            )
            assert getattr(configuration, nom_du_module) is False, nom_du_module
            assert faux_save.call_count == 1, nom_du_module
            assert messages_django.ERROR not in niveaux_des_messages, nom_du_module

    # ------------------------------------------------------------------ #
    #  11 — Admin fedow_core : pages et routes fermées en legacy          #
    # ------------------------------------------------------------------ #

    def test_admin_fedow_core_ferme_en_legacy(self):
        """
        Les pages de l'admin `fedow_core` par leur URL directe (spec §5.3) :
        listes des assets, tokens, transactions et fédérations ; ajout d'un asset et
        d'une fédération ; fiche d'un asset et d'une fédération créés par le lieu.
        - lieu v2 : 200 partout ;
        - lieu legacy : 403 partout.
        / fedow_core admin pages by direct URL: 200 for a v2 venue, 403 for a legacy one.
        """
        asset_du_lieu = self.creer_un_asset_du_lieu("Points verrou")
        federation_du_lieu = self.creer_une_federation_du_lieu("Federation verrou")

        adresses_des_pages = [
            reverse("staff_admin:fedow_core_asset_changelist"),
            reverse("staff_admin:fedow_core_asset_add"),
            reverse("staff_admin:fedow_core_asset_change", args=[asset_du_lieu.pk]),
            reverse("staff_admin:fedow_core_token_changelist"),
            reverse("staff_admin:fedow_core_transaction_changelist"),
            reverse("staff_admin:fedow_core_federation_changelist"),
            reverse("staff_admin:fedow_core_federation_add"),
            reverse(
                "staff_admin:fedow_core_federation_change",
                args=[federation_du_lieu.pk],
            ),
        ]

        reponses_inattendues = []
        for moteur, statut_attendu in [(MOTEUR_V2, 200), (MOTEUR_LEGACY, 403)]:
            self.poser_le_moteur_du_lieu_dedie(moteur)
            navigateur = self.navigateur_connecte()
            for adresse in adresses_des_pages:
                reponse = navigateur.get(adresse)
                if reponse.status_code != statut_attendu:
                    reponses_inattendues.append(
                        f"{moteur} {adresse} : {reponse.status_code} "
                        f"(attendu {statut_attendu})"
                    )

        assert reponses_inattendues == [], "\n".join(reponses_inattendues)

    def test_routes_personnalisees_fedow_core_fermees_en_legacy(self):
        """
        Les routes personnalisées de l'admin `fedow_core` ne lisent pas les permissions
        de l'admin : chacune refuse elle-même un lieu legacy (spec §5.3).
        - accepter une invitation sur un asset ;
        - accepter une invitation dans une fédération ;
        - exclure un membre de sa fédération.
        Lieu v2 : les trois passent (témoin). Lieu legacy : rien ne bouge.
        Le membre à exclure est la ligne `Client` du schéma public (jamais un lieu de démo).
        / Custom routes: they work for a v2 venue; nothing moves for a legacy one.
        """
        lieu_a_exclure = Client.objects.get(schema_name=get_public_schema_name())

        for moteur in [MOTEUR_V2, MOTEUR_LEGACY]:
            # Les objets sont recréés pour chaque moteur : le passage v2 les a modifiés.
            # / Objects are re-created per engine: the v2 pass changed them.
            asset_avec_invitation = self.creer_un_asset_du_lieu("Points invites")
            asset_avec_invitation.pending_invitations.add(self.tenant)

            federation_avec_invitation = Federation.objects.create(
                name=f"Federation invitante {uuid.uuid4().hex[:8]}",
                created_by=self.tenant,
            )
            federation_avec_invitation.pending_tenants.add(self.tenant)

            federation_avec_un_membre = self.creer_une_federation_du_lieu(
                "Federation a deux membres"
            )
            federation_avec_un_membre.tenants.add(lieu_a_exclure)

            self.poser_le_moteur_du_lieu_dedie(moteur)
            navigateur = self.navigateur_connecte()

            navigateur.post(
                reverse(
                    "staff_admin:asset-accept-invitation",
                    args=[asset_avec_invitation.pk],
                )
            )
            navigateur.post(
                reverse(
                    "staff_admin:federation-accept-invitation",
                    args=[federation_avec_invitation.pk],
                )
            )
            navigateur.post(
                reverse(
                    "staff_admin:federation-remove-member",
                    args=[federation_avec_un_membre.pk, lieu_a_exclure.pk],
                )
            )

            invitation_d_asset_acceptee = asset_avec_invitation.federated_with.filter(
                pk=self.tenant.pk
            ).exists()
            invitation_d_asset_en_attente = (
                asset_avec_invitation.pending_invitations.filter(
                    pk=self.tenant.pk
                ).exists()
            )
            invitation_de_federation_acceptee = (
                federation_avec_invitation.tenants.filter(pk=self.tenant.pk).exists()
            )
            invitation_de_federation_en_attente = (
                federation_avec_invitation.pending_tenants.filter(
                    pk=self.tenant.pk
                ).exists()
            )
            membre_toujours_present = federation_avec_un_membre.tenants.filter(
                pk=lieu_a_exclure.pk
            ).exists()

            if moteur == MOTEUR_V2:
                assert invitation_d_asset_acceptee is True, moteur
                assert invitation_d_asset_en_attente is False, moteur
                assert invitation_de_federation_acceptee is True, moteur
                assert invitation_de_federation_en_attente is False, moteur
                assert membre_toujours_present is False, moteur
            else:
                assert invitation_d_asset_acceptee is False, moteur
                assert invitation_d_asset_en_attente is True, moteur
                assert invitation_de_federation_acceptee is False, moteur
                assert invitation_de_federation_en_attente is True, moteur
                assert membre_toujours_present is True, moteur

    # ------------------------------------------------------------------ #
    #  12 — Invitations V2 : un lieu legacy n'est jamais invitable        #
    # ------------------------------------------------------------------ #

    def test_invitation_federation_v2_n_offre_pas_un_lieu_legacy(self):
        """
        Le lieu qui invite est `lespass` (v2), lu en base et jamais modifié. Le lieu
        candidat est le lieu dédié (salle de spectacle), dont seul le moteur change.
        Pour les deux champs d'invitation V2 (spec §5.3) :
        - `AssetAdmin` → `pending_invitations` ;
        - `FederationAdmin` → `pending_tenants`.
        Candidat v2 : présent dans le queryset du champ, et son pk est accepté par le
        champ (témoin). Candidat legacy : absent, et son pk forcé est refusé
        (`ValidationError`) : c'est le queryset qui valide, pas l'autocomplétion.
        Autocomplétion `TenantAdmin.get_search_results`, appelée avec les paramètres GET
        de l'autocomplétion de chacun de ces deux champs : candidat v2 présent, candidat
        legacy absent.
        / The two V2 invitation fields and the autocomplete never offer a legacy venue.
        """
        lieu_qui_invite = Client.objects.get(schema_name="lespass")
        assert lieu_qui_invite.moteur_monnaie == MOTEUR_V2, (
            "lespass doit être v2 (vérification de départ : "
            "tests/outils_moteur_de_monnaie.py)"
        )
        Client.objects.filter(pk=self.tenant.pk).update(
            categorie=Client.SALLE_SPECTACLE
        )

        champs_d_invitation = [
            (Asset, "asset", "pending_invitations"),
            (Federation, "federation", "pending_tenants"),
        ]

        constats_faux = []
        for moteur_du_candidat in [MOTEUR_V2, MOTEUR_LEGACY]:
            Client.objects.filter(pk=self.tenant.pk).update(
                moteur_monnaie=moteur_du_candidat
            )
            candidat_attendu = moteur_du_candidat == MOTEUR_V2

            with tenant_context(lieu_qui_invite):
                for modele, nom_du_modele, nom_du_champ in champs_d_invitation:
                    admin_du_modele = staff_admin_site._registry[modele]
                    requete_du_formulaire = self.construire_une_requete(
                        "get", "/admin/fedow_core/", self.administrateur_du_lieu
                    )
                    champ_du_formulaire = admin_du_modele.formfield_for_manytomany(
                        modele._meta.get_field(nom_du_champ), requete_du_formulaire
                    )

                    candidat_dans_le_queryset = champ_du_formulaire.queryset.filter(
                        pk=self.tenant.pk
                    ).exists()
                    if candidat_dans_le_queryset != candidat_attendu:
                        constats_faux.append(
                            f"{nom_du_modele}.{nom_du_champ}, candidat "
                            f"{moteur_du_candidat} : dans le queryset = "
                            f"{candidat_dans_le_queryset}"
                        )

                    try:
                        champ_du_formulaire.clean([str(self.tenant.pk)])
                        pk_force_accepte = True
                    except ValidationError:
                        pk_force_accepte = False
                    if pk_force_accepte != candidat_attendu:
                        constats_faux.append(
                            f"{nom_du_modele}.{nom_du_champ}, candidat "
                            f"{moteur_du_candidat} : pk forcé accepté = "
                            f"{pk_force_accepte}"
                        )

                    admin_des_lieux = staff_admin_site._registry[Client]
                    requete_d_autocompletion = self.construire_une_requete(
                        "get",
                        "/admin/autocomplete/",
                        self.administrateur_du_lieu,
                        parametres={
                            "app_label": "fedow_core",
                            "model_name": nom_du_modele,
                            "field_name": nom_du_champ,
                            "term": "",
                        },
                    )
                    resultats, _avec_distinct = admin_des_lieux.get_search_results(
                        requete_d_autocompletion,
                        admin_des_lieux.get_queryset(requete_d_autocompletion),
                        "",
                    )
                    candidat_propose = resultats.filter(pk=self.tenant.pk).exists()
                    if candidat_propose != candidat_attendu:
                        constats_faux.append(
                            f"autocomplétion {nom_du_modele}.{nom_du_champ}, candidat "
                            f"{moteur_du_candidat} : proposé = {candidat_propose}"
                        )

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  13 — Points d'entrée V2 : caisse, kiosk, tireuse                   #
    # ------------------------------------------------------------------ #

    def test_points_d_entree_v2_refuses_en_legacy(self):
        """
        Les trois permissions des points d'entrée V2 (spec §5.4), chacune avec un
        appelant qu'elle accepte aujourd'hui :
        - `HasLaBoutikTerminalAccess` : un terminal LaBoutik du lieu, `module_caisse`
          allumé (configuration en mémoire) ;
        - `IsKioskTerminal` : un terminal Kiosque du lieu ;
        - `HasTireuseAccess` : un gestionnaire du lieu connecté.
        Lieu v2 : accès (témoin). Lieu legacy : refus, même drapeau allumé.
        Les terminaux sont des objets en mémoire (le contrôle ne lit que leurs champs).
        / The three V2 entry points: open for v2, refused for legacy (parametrised).
        """
        terminal_laboutik = TibilletUser(
            email="terminal-laboutik-verrou@tibillet.localhost",
            espece=TibilletUser.TYPE_TERM,
            terminal_role=TibilletUser.ROLE_LABOUTIK,
            client_source_id=self.tenant.pk,
            is_active=True,
        )
        terminal_kiosque = TibilletUser(
            email="terminal-kiosque-verrou@tibillet.localhost",
            espece=TibilletUser.TYPE_TERM,
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            client_source_id=self.tenant.pk,
            is_active=True,
        )

        cas_a_verifier = [
            (
                "HasLaBoutikTerminalAccess",
                HasLaBoutikTerminalAccess(),
                terminal_laboutik,
            ),
            ("IsKioskTerminal", IsKioskTerminal(), terminal_kiosque),
            ("HasTireuseAccess", HasTireuseAccess(), self.administrateur_du_lieu),
        ]
        configuration_caisse_allumee = self.configuration_en_memoire(
            ["module_caisse", "module_monnaie_locale"]
        )

        constats_faux = []
        for moteur, acces_attendu in [(MOTEUR_V2, True), (MOTEUR_LEGACY, False)]:
            self.poser_le_moteur_du_lieu_dedie(moteur)
            for nom_de_la_permission, permission, appelant in cas_a_verifier:
                requete = self.construire_une_requete("get", "/", appelant)
                with patch.object(
                    Configuration,
                    "get_solo",
                    return_value=configuration_caisse_allumee,
                ):
                    acces_accorde = permission_accordee(permission, requete)
                if acces_accorde != acces_attendu:
                    constats_faux.append(
                        f"{nom_de_la_permission}, lieu {moteur} : accès = "
                        f"{acces_accorde} (attendu {acces_attendu})"
                    )

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  14 — « Mon compte » : pas de tokens locaux pour un lieu legacy     #
    # ------------------------------------------------------------------ #

    def test_tokens_locaux_de_mon_compte_fermes_en_legacy(self):
        """
        Un utilisateur du lieu a 15,00 points dans un asset `fedow_core` du lieu. La
        monnaie locale est allumée (configuration en mémoire), le Fedow distant ne
        répond pas. On lit les tokens par les deux chemins de « Mon compte » (relecture
        I1) :
        - `get_distant_fedow_tokens` (sert `tokens_table` et l'index V2) ;
        - `MyAccount.admin_my_cards` (fiche admin de l'utilisateur ; le gabarit n'est pas
          rendu, on lit le contexte passé à `render`).
        Lieu v2 : le token local est là (témoin). Lieu legacy : aucun token local.
        / Local fedow_core tokens show for a v2 venue, never for a legacy one.
        """
        portefeuille_de_l_utilisateur = Wallet.objects.create(
            name=f"Portefeuille utilisateur verrou {uuid.uuid4().hex[:8]}"
        )
        utilisateur = self.creer_un_utilisateur(
            prefixe_de_l_email="utilisateur-verrou",
            wallet=portefeuille_de_l_utilisateur,
        )
        utilisateur.client_achat.add(self.tenant)

        asset_local = self.creer_un_asset_du_lieu("Points locaux")
        Token.objects.create(
            wallet=portefeuille_de_l_utilisateur,
            asset=asset_local,
            value=1500,
        )
        configuration_monnaie_locale_allumee = self.configuration_en_memoire(
            ["module_monnaie_locale"]
        )

        def uuids_des_tokens_locaux(liste_de_tokens):
            uuids_trouves = []
            for token in liste_de_tokens:
                if token.get("is_local"):
                    uuids_trouves.append(token["asset"]["uuid"])
            return uuids_trouves

        constats_faux = []
        for moteur, tokens_locaux_attendus in [
            (MOTEUR_V2, [str(asset_local.uuid)]),
            (MOTEUR_LEGACY, []),
        ]:
            self.poser_le_moteur_du_lieu_dedie(moteur)

            # Chemin 1 : get_distant_fedow_tokens. / Path 1.
            requete_du_compte = self.construire_une_requete(
                "get", "/my_account/tokens_table/", utilisateur
            )
            with faux_fedow_distant_injoignable():
                tokens_du_compte = get_distant_fedow_tokens(
                    requete_du_compte, configuration_monnaie_locale_allumee
                )
            if uuids_des_tokens_locaux(tokens_du_compte) != tokens_locaux_attendus:
                constats_faux.append(
                    f"get_distant_fedow_tokens, lieu {moteur} : "
                    f"{uuids_des_tokens_locaux(tokens_du_compte)} "
                    f"(attendu {tokens_locaux_attendus})"
                )

            # Chemin 2 : admin_my_cards. / Path 2.
            requete_de_la_fiche = self.construire_une_requete(
                "get",
                f"/my_account/{utilisateur.pk}/admin_my_cards/",
                self.administrateur_du_lieu,
            )
            with faux_fedow_distant_injoignable():
                with patch.object(
                    Configuration,
                    "get_solo",
                    return_value=configuration_monnaie_locale_allumee,
                ):
                    with patch("BaseBillet.views.render") as faux_render:
                        MyAccount().admin_my_cards(
                            requete_de_la_fiche, pk=str(utilisateur.pk)
                        )
            tokens_de_la_fiche = faux_render.call_args.kwargs["context"]["tokens"]
            if uuids_des_tokens_locaux(tokens_de_la_fiche) != tokens_locaux_attendus:
                constats_faux.append(
                    f"admin_my_cards, lieu {moteur} : "
                    f"{uuids_des_tokens_locaux(tokens_de_la_fiche)} "
                    f"(attendu {tokens_locaux_attendus})"
                )

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  15 — api/inventaire/ reste ouvert en legacy                        #
    # ------------------------------------------------------------------ #

    def test_api_inventaire_reste_ouvert_en_legacy(self):
        """
        `api/inventaire/` ne déplace pas d'argent : il reste ouvert à un lieu legacy
        (spec §5.7, relecture). Ses deux vues gardent `HasLaBoutikAccess`, qui laisse
        passer un gestionnaire du lieu legacy. `HasLaBoutikAccess` sert aussi les routes
        LaBoutik V1 : elle ne doit pas lire le moteur.
        / api/inventaire/ (no money) stays open for a legacy venue.
        """
        assert StockViewSet.permission_classes == [HasLaBoutikAccess]
        assert DebitMetreViewSet.permission_classes == [HasLaBoutikAccess]

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        requete = self.construire_une_requete(
            "get", "/api/inventaire/stock/", self.administrateur_du_lieu
        )

        assert permission_accordee(HasLaBoutikAccess(), requete) is True

    # ------------------------------------------------------------------ #
    #  23 — Appairage LaBoutik V1 : refusé sur un lieu v2 (I1)            #
    # ------------------------------------------------------------------ #

    def test_lieu_v2_ne_peut_pas_appairer_une_caisse_v1(self):
        """
        `Onboard_laboutik` (POST d'une caisse LaBoutik V1 qui s'appaire) :
        - lieu v2, modules V2 éteints : refus 409 au format des autres refus de la vue
          (`detail` + `code`), avant tout appel au Fedow et sans rien écrire (pas de
          `save()`, `server_cashless` et `key_cashless` restent vides) ;
        - lieu legacy, modules V2 éteints (témoin, comme avant) : la vue passe ses verrous
          et appelle le Fedow pour lier la caisse à la place.
        La `Configuration` est un objet en mémoire (`get_solo()` et `save()` patchés). Le
        Fedow est un faux qui lève une erreur dédiée dès qu'on le construit : on sait
        ainsi que la vue a passé les verrous, sans aucun appel réseau.
        / v2 venue: V1 pairing refused (409), nothing written, Fedow never called.
        Legacy venue: the view goes on to the Fedow call, as before.
        """

        class LeFedowEstAppele(Exception):
            """Levée par le faux Fedow : la vue a passé ses verrous.
            / Raised by the fake Fedow: the view went past its locks."""

        charge_utile_de_la_caisse_v1 = {
            "server_cashless": "https://laboutik-v1.example.org",
            "key_cashless": "peu-importe",
            "pum_pem_cashless": "peu-importe",
            "email": self.administrateur_du_lieu.email,
        }
        vue_d_appairage = Onboard_laboutik.as_view()

        def appairer_une_caisse_v1(configuration):
            requete = self.fabrique_de_requetes.post(
                "/api/onboard_laboutik/", data=charge_utile_de_la_caisse_v1
            )
            with patch.object(Configuration, "get_solo", return_value=configuration):
                with patch.object(Configuration, "save", autospec=True) as faux_save:
                    with patch(
                        "ApiBillet.views.FedowAPI", side_effect=LeFedowEstAppele
                    ) as faux_fedow:
                        try:
                            reponse = vue_d_appairage(requete)
                        except LeFedowEstAppele:
                            reponse = None
            return reponse, faux_save, faux_fedow

        # Lieu v2 : refus, rien écrit. / v2 venue: refused, nothing written.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration_du_lieu_v2 = self.configuration_en_memoire([])
        reponse, faux_save, faux_fedow = appairer_une_caisse_v1(
            configuration_du_lieu_v2
        )
        assert reponse is not None, "lieu v2 : la vue a appelé le Fedow (pas de refus)"
        assert reponse.status_code == 409
        assert reponse.data["code"] == "lieu_en_moteur_v2"
        assert str(reponse.data["detail"]) != ""
        assert faux_fedow.call_count == 0
        assert faux_save.call_count == 0
        assert not configuration_du_lieu_v2.server_cashless
        assert not configuration_du_lieu_v2.key_cashless

        # Lieu legacy : comme avant. / Legacy venue: as before.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        reponse, _faux_save, faux_fedow = appairer_une_caisse_v1(
            self.configuration_en_memoire([])
        )
        assert reponse is None, (
            f"lieu legacy : appairage refusé ({getattr(reponse, 'status_code', None)})"
        )
        assert faux_fedow.call_count == 1

    # ------------------------------------------------------------------ #
    #  24 (1/2) — La vérification de départ de la suite (I2)             #
    # ------------------------------------------------------------------ #

    def test_verification_de_depart_automatique(self):
        """
        La fonction de la fixture autouse `_moteurs_verifies_au_depart_de_la_suite`
        (`tests/outils_moteur_de_monnaie.py`, `verifier_le_depart_de_la_suite`) :
        - état normal (le lieu dédié `test_*` en v2) : elle passe, avec au plus une
          requête sur la table des lieux (`Customers_client`) ;
        - le lieu dédié `test_*` posé en legacy (transaction du test, annulée à la fin) :
          elle échoue (`pytest.fail`, jamais `skip`), en nommant le lieu et en donnant la
          consigne (`down -v`).
        `lespass` n'est jamais modifié : son cas se lit dans la même requête.
        / Normal state: passes, at most one query on the venues table. A `test_*` venue
        in legacy: fails with the instructions.
        """
        module_des_outils = importlib.import_module("tests.outils_moteur_de_monnaie")
        verifier_le_depart_de_la_suite = module_des_outils.verifier_le_depart_de_la_suite

        # On ne compte que les requêtes sur la table des lieux : une autre requête
        # (un SAVEPOINT, une lecture du cache des contenus) ne dit rien de la
        # vérification et ne doit pas faire échouer le test.
        # / Only queries on the venues table are counted; any other query is noise.
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=MOTEUR_V2)
        with CaptureQueriesContext(connection) as requetes_de_la_verification:
            verifier_le_depart_de_la_suite()
        requetes_sur_la_table_des_lieux = []
        for requete in requetes_de_la_verification.captured_queries:
            if '"Customers_client"' in requete["sql"]:
                requetes_sur_la_table_des_lieux.append(requete["sql"])
        assert len(requetes_sur_la_table_des_lieux) <= 1, requetes_sur_la_table_des_lieux

        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=MOTEUR_LEGACY)
        with pytest.raises(pytest.fail.Exception) as echec_de_la_verification:
            verifier_le_depart_de_la_suite()
        message_de_l_echec = str(echec_de_la_verification.value)
        assert self.get_test_schema_name() in message_de_l_echec
        assert "down -v" in message_de_l_echec

    # ------------------------------------------------------------------ #
    #  29 — Suppression d'une fédération et save_related (M5)             #
    # ------------------------------------------------------------------ #

    def test_suppression_federation_fermee_en_legacy(self):
        """
        `FederationAdmin.has_delete_permission` : la page de suppression d'une fédération
        créée par le lieu répond 200 en v2 (témoin) et 403 en legacy ; le POST de
        suppression d'un lieu legacy ne supprime rien.
        / Federation delete page: 200 for v2, 403 for legacy; a legacy POST deletes nothing.
        """
        federation_du_lieu = self.creer_une_federation_du_lieu("Federation a supprimer")
        adresse_de_suppression = reverse(
            "staff_admin:fedow_core_federation_delete", args=[federation_du_lieu.pk]
        )

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        assert self.navigateur_connecte().get(adresse_de_suppression).status_code == 200

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        navigateur = self.navigateur_connecte()
        assert navigateur.get(adresse_de_suppression).status_code == 403
        reponse_du_post = navigateur.post(adresse_de_suppression, {"post": "yes"})
        assert reponse_du_post.status_code == 403
        assert Federation.objects.filter(pk=federation_du_lieu.pk).exists()

    def test_save_related_retire_un_lieu_legacy_invite(self):
        """
        `AssetAdmin.save_related`, défense en profondeur : un lieu legacy arrivé dans
        `pending_invitations` par un autre chemin que le formulaire en est retiré ; un lieu
        v2 reste invité (témoin).
        Le faux formulaire simule l'enregistrement M2M de Django (`save_m2m`), qui pose les
        deux invitations. Le lieu legacy est la ligne `Client` du schéma public, passée en
        legacy par `update()` dans la transaction du test (annulée) ; le lieu v2 invité est
        le lieu dédié, créateur de l'asset. Aucun lieu de démo n'est touché.
        / A legacy venue that reached pending_invitations is removed; a v2 one stays.
        """
        lieu_createur_v2 = self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        lieu_public = Client.objects.get(schema_name=get_public_schema_name())
        Client.objects.filter(pk=lieu_public.pk).update(moteur_monnaie=MOTEUR_LEGACY)

        asset_du_lieu = self.creer_un_asset_du_lieu("Points save_related")

        def save_m2m_qui_invite_les_deux_lieux():
            asset_du_lieu.pending_invitations.add(lieu_createur_v2, lieu_public)

        faux_formulaire = SimpleNamespace(
            instance=asset_du_lieu, save_m2m=save_m2m_qui_invite_les_deux_lieux
        )
        requete = self.construire_une_requete(
            "post", "/admin/fedow_core/asset/", self.administrateur_du_lieu
        )

        staff_admin_site._registry[Asset].save_related(
            requete, faux_formulaire, [], True
        )

        lieux_invites = set(
            asset_du_lieu.pending_invitations.values_list("pk", flat=True)
        )
        assert lieu_public.pk not in lieux_invites
        assert lieu_createur_v2.pk in lieux_invites

    # ------------------------------------------------------------------ #
    #  30 — Une monnaie archivée ne s'accepte plus (relecture Fable M-1)  #
    # ------------------------------------------------------------------ #

    def test_asset_archive_absent_des_invitations_et_refuse(self):
        """
        Une monnaie `fedow_core` archivée n'est plus proposée au partage :
        - le panneau des invitations de la liste des assets ne la montre pas ;
        - la route « accepter l'invitation » la refuse : le lieu reste en attente et
          n'est pas ajouté aux lieux qui partagent la monnaie.
        Témoin : une monnaie invitée NON archivée est montrée, puis acceptée.
        La monnaie archivée garde `active=True` : c'est l'état laissé par les E2E de
        fédération (archivée, mais pas bloquée).
        / An archived fedow_core asset is not shown in the invitations panel and its
        acceptance is refused. Control: a non-archived invited asset is shown and accepted.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)

        asset_invite_non_archive = self.creer_un_asset_du_lieu("Points invites actifs")
        asset_invite_non_archive.pending_invitations.add(self.tenant)

        asset_invite_archive = self.creer_un_asset_du_lieu("Points invites archives")
        asset_invite_archive.pending_invitations.add(self.tenant)
        # `update()` : l'archivage ne passe pas par le signal post_save (aucun produit
        # de recharge à archiver pour une monnaie FID).
        # / update(): archiving skips the post_save signal.
        Asset.objects.filter(pk=asset_invite_archive.pk).update(
            archive=True, active=True
        )

        navigateur = self.navigateur_connecte()

        # Les écarts sont relevés puis vérifiés ensemble : un échec montre à la fois
        # le panneau et la route.
        # / Gaps are collected then checked together: a failure shows both.
        ecarts_constates = []

        # 1. Le panneau des invitations / The invitations panel
        reponse_de_la_liste = navigateur.get(
            reverse("staff_admin:fedow_core_asset_changelist")
        )
        assert reponse_de_la_liste.status_code == 200
        html_de_la_liste = reponse_de_la_liste.content.decode()
        assert f'data-testid="asset-invitation-{asset_invite_non_archive.pk}"' in (
            html_de_la_liste
        ), "Témoin : la monnaie invitée non archivée doit être dans le panneau."
        if f'data-testid="asset-invitation-{asset_invite_archive.pk}"' in (
            html_de_la_liste
        ):
            ecarts_constates.append(
                "panneau : la monnaie archivée est proposée dans les invitations"
            )

        # 2. La route d'acceptation / The acceptance route
        for asset_invite in [asset_invite_non_archive, asset_invite_archive]:
            navigateur.post(
                reverse("staff_admin:asset-accept-invitation", args=[asset_invite.pk])
            )

        assert asset_invite_non_archive.federated_with.filter(
            pk=self.tenant.pk
        ).exists(), "Témoin : l'invitation non archivée doit être acceptée."

        monnaie_archivee_partagee = asset_invite_archive.federated_with.filter(
            pk=self.tenant.pk
        ).exists()
        monnaie_archivee_toujours_en_attente = (
            asset_invite_archive.pending_invitations.filter(pk=self.tenant.pk).exists()
        )
        if monnaie_archivee_partagee:
            ecarts_constates.append(
                "route : l'acceptation de la monnaie archivée a été acceptée"
            )
        if not monnaie_archivee_toujours_en_attente:
            ecarts_constates.append(
                "route : le lieu n'est plus en attente sur la monnaie archivée"
            )

        assert ecarts_constates == [], "\n".join(ecarts_constates)


# ==========================================================================
# 3e PARTIE — L'AFFICHAGE DU VERROU (tests 16 à 22)
# / PART 3 — THE LOCK ON SCREEN (tests 16 to 22)
# ==========================================================================

# Les modules qui ont une carte au tableau de bord : toutes les clés de MODULE_FIELDS,
# plus `module_inventaire` (pas de carte, mais un drapeau de la Configuration).
# / Every module flag the dashboard and the sidebar read.
TOUS_LES_DRAPEAUX_DE_MODULE = list(dashboard.MODULE_FIELDS.keys()) + [
    "module_inventaire"
]

# Les sections du menu qui n'existent que pour un lieu v2 (spec §5.5).
# / Sidebar sections that exist only for a v2 venue.
SLUGS_DES_SECTIONS_V2 = ["caisse", "terminaux", "inventaire", "tireuses", "kiosk"]

# La section « Monnaies » et la section « Fédération » du menu.
# / The "Currencies" and "Federation" sidebar sections.
SLUG_DE_LA_SECTION_MONNAIES = "monnaies"
SLUG_DE_LA_SECTION_FEDERATION = "federation"


def adresse_des_assets_legacy():
    """La liste de l'admin des assets legacy. / The legacy assets admin list."""
    return reverse("staff_admin:fedow_public_assetfedowpublic_changelist")


def liens_de_la_section(section):
    """Les adresses des pages d'une section du menu. / A section's page links."""
    liens = []
    for page in section.get("items") or []:
        liens.append(str(page.get("link") or ""))
    return liens


class TestAffichageDuVerrou(FastTenantTestCase):
    """
    L'affichage du verrou, dans le lieu dédié `test_verrou_moteur_legacy`.
    / The lock on screen, in the dedicated test venue.

    SIMULATIONS
    - Le moteur du lieu est posé en base par `update()`, puis la connexion reçoit le
      `Client` relu en base (comme le middleware à chaque requête HTTP).
    - La `Configuration` est un objet EN MÉMOIRE, servi par `get_solo()` patché ; `save()`
      est patché aussi. Rien n'est écrit dans la base ni dans memcached.
    - Les assets legacy (`AssetFedowPublic`, schéma public) sont créés dans un point de
      sauvegarde annulé à la fin de chaque cas, dans la transaction du test, annulée à
      son tour. Jamais un lieu de démo comme origine : le lieu dédié, ou la ligne `Client`
      du schéma public.
    / Engine set by update(); in-memory Configuration; legacy assets created in a
    rolled-back savepoint.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_verrou_moteur_legacy"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-verrou-moteur-legacy.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test verrou moteur legacy"

    def setUp(self):
        # La transaction du test précédent a été annulée : on se replace sur le lieu.
        # / Back on the venue after the previous rolled-back test.
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

        # Le lieu dédié ne doit avoir aucun asset legacy au départ : chaque cas pose le
        # sien. / The venue must start with no legacy asset.
        assets_legacy_du_lieu_au_depart = AssetFedowPublic.objects.filter(
            origin=self.tenant
        ) | AssetFedowPublic.objects.filter(
            federated_with=self.tenant
        ) | AssetFedowPublic.objects.filter(pending_invitations=self.tenant)
        assert not assets_legacy_du_lieu_au_depart.exists(), (
            "Le lieu test_verrou_moteur_legacy a déjà un asset legacy en base : "
            "un test précédent l'a laissé. À retirer avant de lancer ce fichier."
        )

    def tearDown(self):
        connection.set_tenant(self.tenant)
        Configuration.clear_cache()

    # ------------------------------------------------------------------ #
    #  Outils / Helpers                                                   #
    # ------------------------------------------------------------------ #

    def poser_le_moteur_du_lieu_dedie(self, moteur):
        """
        Pose le moteur du lieu dédié en base par `update()`, puis place la connexion sur
        le `Client` relu en base.
        / Sets the engine by update(), then puts the re-read Client on the connection.
        """
        Client.objects.filter(pk=self.tenant.pk).update(moteur_monnaie=moteur)
        connection.set_tenant(Client.objects.get(pk=self.tenant.pk))

    def configuration_en_memoire(self, modules_allumes, **autres_valeurs):
        """
        Une `Configuration` en mémoire, jamais enregistrée : tous les modules éteints
        sauf ceux de la liste. Pas de serveur LaBoutik V1 sauf s'il est donné.
        / An in-memory Configuration: every module off except the listed ones.
        """
        valeurs = {"server_cashless": None, "key_cashless": None}
        valeurs.update(autres_valeurs)
        configuration = Configuration(
            pk=Configuration.singleton_instance_id,
            organisation="Test verrou moteur legacy",
            slug="test-verrou-moteur-legacy",
            **valeurs,
        )
        for nom_du_module in TOUS_LES_DRAPEAUX_DE_MODULE:
            setattr(configuration, nom_du_module, nom_du_module in modules_allumes)
        return configuration

    def cartes_par_module(self, configuration):
        """
        Les cartes du tableau de bord, rangées par drapeau de module. La carte caisse
        (type `pos`) est rangée sous `module_caisse`.
        / Dashboard cards indexed by module flag; the POS card under module_caisse.
        """
        with patch.object(Configuration, "get_solo", return_value=configuration):
            cartes = dashboard._build_modules_context(configuration)

        cartes_par_drapeau = {}
        for carte in cartes:
            if carte.get("type") == "pos":
                cartes_par_drapeau["module_caisse"] = carte
            elif carte.get("field"):
                cartes_par_drapeau[carte["field"]] = carte
        return cartes_par_drapeau

    def html_de_la_carte(self, carte):
        """Le HTML d'une carte, rendu en français. / A card's HTML, rendered in French."""
        with translation.override("fr"):
            return render_to_string(
                "admin/partials/dashboard_module_card.html", {"carte": carte}
            )

    def phrase_du_verrou_en_html(self):
        """La phrase du verrou, telle qu'elle sort du gabarit (échappée).
        / The lock sentence, as the template outputs it (escaped)."""
        with translation.override("fr"):
            return escape(str(MESSAGE_MODULE_FERME_AUX_LIEUX_LEGACY))

    def sections_par_slug(self, configuration):
        """Les sections du menu latéral, par slug. / Sidebar sections by slug."""
        with patch.object(Configuration, "get_solo", return_value=configuration):
            sections = dashboard._construire_sections_modules(
                RequestFactory().get("/admin/")
            )
        sections_trouvees = {}
        for section in sections:
            if section.get("_slug"):
                sections_trouvees[section["_slug"]] = section
        return sections_trouvees, sections

    @contextlib.contextmanager
    def un_asset_legacy_le_temps_du_bloc(
        self,
        lien_avec_le_lieu,
        categorie=AssetFedowPublic.TOKEN_LOCAL_FIAT,
        archive=False,
    ):
        """
        Crée un asset legacy relié au lieu dédié, dans un point de sauvegarde annulé à la
        sortie du bloc.
        - « origine » : le lieu dédié est l'origine ;
        - « federe »  : l'origine est la ligne `Client` du schéma public, le lieu dédié est
          dans `federated_with` ;
        - « invite »  : même origine, le lieu dédié est dans `pending_invitations`.
        / Creates a legacy asset linked to the venue, inside a rolled-back savepoint.
        """
        lieu_public = Client.objects.get(schema_name=get_public_schema_name())
        with transaction.atomic():
            portefeuille_d_origine = Wallet.objects.create(
                name=f"Portefeuille asset legacy {uuid.uuid4().hex[:8]}"
            )
            if lien_avec_le_lieu == "origine":
                lieu_d_origine = self.tenant
            else:
                lieu_d_origine = lieu_public
            asset_legacy = AssetFedowPublic.objects.create(
                name=f"Asset legacy verrou {uuid.uuid4().hex[:8]}",
                currency_code="TVL",
                wallet_origin=portefeuille_d_origine,
                origin=lieu_d_origine,
                category=categorie,
                archive=archive,
            )
            if lien_avec_le_lieu == "federe":
                asset_legacy.federated_with.add(self.tenant)
            if lien_avec_le_lieu == "invite":
                asset_legacy.pending_invitations.add(self.tenant)

            yield asset_legacy

            transaction.set_rollback(True)

    # ------------------------------------------------------------------ #
    #  16 — Les cartes des modules V2 sont fermées en legacy              #
    # ------------------------------------------------------------------ #

    def test_cartes_v2_fermees_en_legacy(self):
        """
        Tous les modules éteints (spec §5.2) :
        - lieu legacy : les 4 cartes V2, carte caisse comprise, portent
          `moteur_legacy`, n'ont pas d'interrupteur, et leur HTML montre la phrase du
          verrou, sans interrupteur ni pastille « V1 active » ;
        - lieu legacy avec un serveur LaBoutik V1 : la carte caisse reste `v1_active`
          (lien V1, pastille V1, pas la phrase du verrou) ; les 3 autres restent fermées ;
        - lieu v2 (témoin) : aucune carte fermée, 4 interrupteurs, pas de phrase.
        / Legacy: the 4 V2 cards are closed (POS included, except v1_active); v2 unchanged.
        """
        phrase_du_verrou = self.phrase_du_verrou_en_html()
        constats_faux = []

        # Lieu legacy, aucun serveur V1. / Legacy venue, no V1 server.
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        cartes = self.cartes_par_module(self.configuration_en_memoire([]))
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            carte = cartes[nom_du_module]
            html = self.html_de_la_carte(carte)
            if carte.get("moteur_legacy") is not True:
                constats_faux.append(f"legacy, {nom_du_module} : pas de moteur_legacy")
            if carte.get("montre_interrupteur"):
                constats_faux.append(f"legacy, {nom_du_module} : interrupteur montré")
            if phrase_du_verrou not in html:
                constats_faux.append(f"legacy, {nom_du_module} : phrase absente du HTML")
            if 'role="switch"' in html:
                constats_faux.append(f"legacy, {nom_du_module} : interrupteur dans le HTML")
            if "dashboard-card-pos-v1-badge" in html:
                constats_faux.append(f"legacy, {nom_du_module} : pastille « V1 active »")

        # Lieu legacy avec LaBoutik V1. / Legacy venue with LaBoutik V1.
        adresse_du_serveur_v1 = "https://laboutik-v1.example.org"
        cartes = self.cartes_par_module(
            self.configuration_en_memoire([], server_cashless=adresse_du_serveur_v1)
        )
        carte_caisse_v1 = cartes["module_caisse"]
        html_caisse_v1 = self.html_de_la_carte(carte_caisse_v1)
        if carte_caisse_v1.get("state") != "v1_active":
            constats_faux.append(f"legacy V1, caisse : état {carte_caisse_v1.get('state')}")
        if carte_caisse_v1.get("moteur_legacy"):
            constats_faux.append("legacy V1, caisse : fermée par le verrou")
        if carte_caisse_v1.get("montre_interrupteur"):
            constats_faux.append("legacy V1, caisse : interrupteur montré")
        if carte_caisse_v1.get("lien_externe") != adresse_du_serveur_v1:
            constats_faux.append("legacy V1, caisse : lien V1 perdu")
        if "dashboard-card-pos-v1-badge" not in html_caisse_v1:
            constats_faux.append("legacy V1, caisse : pastille « V1 active » absente")
        if phrase_du_verrou in html_caisse_v1:
            constats_faux.append("legacy V1, caisse : phrase du verrou affichée")
        for nom_du_module in ["module_monnaie_locale", "module_kiosk", "module_tireuse"]:
            if cartes[nom_du_module].get("moteur_legacy") is not True:
                constats_faux.append(f"legacy V1, {nom_du_module} : pas fermée")

        # Lieu v2 (témoin). / v2 venue (control).
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        cartes = self.cartes_par_module(self.configuration_en_memoire([]))
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            carte = cartes[nom_du_module]
            html = self.html_de_la_carte(carte)
            if carte.get("moteur_legacy"):
                constats_faux.append(f"v2, {nom_du_module} : fermée par le verrou")
            if not carte.get("montre_interrupteur"):
                constats_faux.append(f"v2, {nom_du_module} : pas d'interrupteur")
            if 'role="switch"' not in html:
                constats_faux.append(f"v2, {nom_du_module} : interrupteur absent du HTML")
            if phrase_du_verrou in html:
                constats_faux.append(f"v2, {nom_du_module} : phrase du verrou affichée")

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  17 — Un module V2 resté allumé garde un interrupteur (Q2)          #
    # ------------------------------------------------------------------ #

    def test_module_v2_allume_en_legacy_garde_un_interrupteur_pour_eteindre(self):
        """
        Lieu legacy dont les 4 modules V2 sont restés allumés en base (décision Q2 :
        « interrupteur visible seulement pour éteindre ») : chaque carte montre un
        interrupteur allumé (le serveur accepte l'extinction, test 9).
        / Legacy venue with V2 modules still on: each card keeps a switch, set to on.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        cartes = self.cartes_par_module(
            self.configuration_en_memoire(DRAPEAUX_DES_MODULES_V2)
        )

        constats_faux = []
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            carte = cartes[nom_du_module]
            html = self.html_de_la_carte(carte)
            if not carte.get("montre_interrupteur"):
                constats_faux.append(f"{nom_du_module} : pas d'interrupteur")
            if not carte.get("allume"):
                constats_faux.append(f"{nom_du_module} : interrupteur éteint")
            if 'role="switch"' not in html or 'aria-checked="true"' not in html:
                constats_faux.append(f"{nom_du_module} : interrupteur allumé absent du HTML")

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  18 — Pas de lien d'ouverture V2 en legacy ; compteur juste         #
    # ------------------------------------------------------------------ #

    def test_carte_tireuse_sans_open_kiosk_en_legacy(self):
        """
        La carte tireuse d'un lieu legacy n'a pas de lien « Open kiosk », module éteint
        ou resté allumé. Même chose pour « Open POS » sur une caisse V2 restée allumée :
        la caisse V2 refuse un lieu legacy (test 13), le lien mènerait à un refus.
        Lieu v2 (témoin) : la tireuse garde « Open kiosk », la caisse allumée « Open POS ».
        / Legacy: no "Open kiosk" on the tap card, no "Open POS"; v2 keeps both.
        """
        constats_faux = []

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        for modules_allumes in [[], DRAPEAUX_DES_MODULES_V2]:
            cartes = self.cartes_par_module(
                self.configuration_en_memoire(modules_allumes)
            )
            etat = "allumés" if modules_allumes else "éteints"
            if cartes["module_tireuse"].get("lien_externe"):
                constats_faux.append(f"legacy, modules {etat} : « Open kiosk » présent")
            if cartes["module_caisse"].get("lien_externe"):
                constats_faux.append(f"legacy, modules {etat} : « Open POS » présent")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        cartes = self.cartes_par_module(
            self.configuration_en_memoire(DRAPEAUX_DES_MODULES_V2)
        )
        if cartes["module_tireuse"].get("lien_externe") != "/controlvanne/kiosk/":
            constats_faux.append("v2 : « Open kiosk » absent")
        if cartes["module_caisse"].get("lien_externe") != "/laboutik/caisse/":
            constats_faux.append("v2 : « Open POS » absent")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_compteur_des_cartes_eteintes_sans_les_cartes_fermees(self):
        """
        La pastille « Découvrir plus de modules » compte les modules éteints qu'on peut
        allumer. Tous les modules éteints : en legacy, elle compte 4 de moins qu'en v2
        (les 4 cartes fermées par le verrou ne s'allument pas). Lu dans le contexte du
        tableau de bord (`dashboard_callback`).
        / The "discover more" pill skips the 4 closed cards in legacy.
        """
        configuration = self.configuration_en_memoire([])

        def modules_eteints_du_tableau_de_bord():
            requete = RequestFactory().get("/admin/")
            with patch.object(Configuration, "get_solo", return_value=configuration):
                contexte = dashboard.dashboard_callback(requete, {})
            return contexte["modules_eteints"]

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        modules_eteints_en_v2 = modules_eteints_du_tableau_de_bord()
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        modules_eteints_en_legacy = modules_eteints_du_tableau_de_bord()

        assert modules_eteints_en_v2 - modules_eteints_en_legacy == 4, (
            f"v2 : {modules_eteints_en_v2}, legacy : {modules_eteints_en_legacy}"
        )

    # ------------------------------------------------------------------ #
    #  19 — Menu : les sections V2 n'existent que pour un lieu v2         #
    # ------------------------------------------------------------------ #

    def test_menu_sections_v2_absentes_en_legacy(self):
        """
        Les 4 modules V2 allumés en base (et la fédération) :
        - lieu v2 : sections caisse, terminaux, inventaire, tireuses, kiosk présentes ;
        - lieu legacy : toutes absentes, et aucune page `fedow_core` dans tout le menu.
        / V2 sections exist only for a v2 venue; no fedow_core page in a legacy menu.
        """
        configuration = self.configuration_en_memoire(
            DRAPEAUX_DES_MODULES_V2 + ["module_federation"]
        )
        constats_faux = []

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        sections_v2, _toutes = self.sections_par_slug(configuration)
        for slug in SLUGS_DES_SECTIONS_V2:
            if slug not in sections_v2:
                constats_faux.append(f"v2 : section « {slug} » absente")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        sections_legacy, toutes_les_sections_legacy = self.sections_par_slug(
            configuration
        )
        for slug in SLUGS_DES_SECTIONS_V2:
            if slug in sections_legacy:
                constats_faux.append(f"legacy : section « {slug} » présente")
        for section in toutes_les_sections_legacy:
            for lien in liens_de_la_section(section):
                if lien.startswith("/admin/fedow_core/"):
                    constats_faux.append(
                        f"legacy : {lien} dans « {section.get('title')} »"
                    )

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  20 — Menu : la section « Monnaies » suit le moteur                 #
    # ------------------------------------------------------------------ #

    def test_section_monnaies_suit_le_moteur(self):
        """
        La section « Monnaies » (slug `monnaies`, spec §5.5, décision Q1) :
        - v2, monnaie locale allumée, sans asset legacy : pages `fedow_core`, pas
          d'« Assets legacy » ;
        - v2, monnaie locale allumée, avec un asset legacy (le lieu en est l'origine, ou
          fédéré, ou invité) : « Assets legacy » en plus, dans l'onglet « Gérer », titre
          avec « legacy » ;
        - v2, assets legacy exclus (badge BDG, adhésion SUB, archivé) : pas d'« Assets
          legacy » ;
        - v2, monnaie locale éteinte, invité sur un asset legacy : seulement « Assets
          legacy » ; sans asset legacy : pas de section ;
        - legacy + fédération (monnaie locale restée allumée en base) : seulement « Assets
          legacy », titre de la section inchangé ;
        - legacy sans fédération mais invité sur un asset legacy : seulement « Assets
          legacy » ;
        - legacy sans fédération ni asset legacy : pas de section.
        / The "Currencies" section follows the engine and the venue's legacy assets.
        """
        adresse_assets_legacy = adresse_des_assets_legacy()
        carte_des_liens = dashboard._carte_des_liens_vers_modeles()
        constats_faux = []

        def section_monnaies(configuration):
            sections, _toutes = self.sections_par_slug(configuration)
            return sections.get(SLUG_DE_LA_SECTION_MONNAIES)

        # --- Lieu v2 / v2 venue ---
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration_v2 = self.configuration_en_memoire(["module_monnaie_locale"])

        section = section_monnaies(configuration_v2)
        if section is None:
            constats_faux.append("v2 sans asset legacy : section absente")
        else:
            liens = liens_de_la_section(section)
            if reverse("staff_admin:fedow_core_asset_changelist") not in liens:
                constats_faux.append("v2 sans asset legacy : « Monnaies et tokens » absent")
            if adresse_assets_legacy in liens:
                constats_faux.append("v2 sans asset legacy : « Assets legacy » présent")

        for lien_avec_le_lieu in ["origine", "federe", "invite"]:
            with self.un_asset_legacy_le_temps_du_bloc(lien_avec_le_lieu):
                section = section_monnaies(configuration_v2)
            cas = f"v2, asset legacy ({lien_avec_le_lieu})"
            if section is None:
                constats_faux.append(f"{cas} : section absente")
                continue
            pages_assets_legacy = [
                page
                for page in section["items"]
                if str(page.get("link")) == adresse_assets_legacy
            ]
            if len(pages_assets_legacy) != 1:
                constats_faux.append(f"{cas} : « Assets legacy » absent")
                continue
            if "legacy" not in str(pages_assets_legacy[0].get("title")).lower():
                constats_faux.append(f"{cas} : titre sans « legacy »")
            if reverse("staff_admin:fedow_core_asset_changelist") not in liens_de_la_section(section):
                constats_faux.append(f"{cas} : « Monnaies et tokens » absent")
            pages_de_gerer = dashboard._categoriser_les_pages(
                section["items"], carte_des_liens
            ).get("gerer", [])
            liens_de_gerer = [str(page.get("link")) for page in pages_de_gerer]
            if adresse_assets_legacy not in liens_de_gerer:
                constats_faux.append(f"{cas} : « Assets legacy » hors de « Gérer »")

        cas_exclus = [
            ("badge BDG", {"categorie": AssetFedowPublic.BADGE}),
            ("adhésion SUB", {"categorie": AssetFedowPublic.SUBSCRIPTION}),
            ("archivé", {"archive": True}),
        ]
        for nom_du_cas, parametres in cas_exclus:
            with self.un_asset_legacy_le_temps_du_bloc("origine", **parametres):
                section = section_monnaies(configuration_v2)
            if section is not None and adresse_assets_legacy in liens_de_la_section(section):
                constats_faux.append(f"v2, asset {nom_du_cas} : « Assets legacy » présent")

        # v2, monnaie locale éteinte : la section n'existe que pour les assets legacy
        # (décision Q1 : une seule porte ; l'invitation reste acceptable).
        # / v2, local currency off: the section exists only for the legacy assets.
        configuration_v2_sans_monnaie_locale = self.configuration_en_memoire([])
        with self.un_asset_legacy_le_temps_du_bloc("invite"):
            section = section_monnaies(configuration_v2_sans_monnaie_locale)
        if section is None:
            constats_faux.append("v2 invité, monnaie locale éteinte : section absente")
        elif liens_de_la_section(section) != [adresse_assets_legacy]:
            constats_faux.append(
                f"v2 invité, monnaie locale éteinte : pages {liens_de_la_section(section)}"
            )
        if section_monnaies(configuration_v2_sans_monnaie_locale) is not None:
            constats_faux.append("v2 sans monnaie locale ni asset : section présente")

        # --- Lieu legacy / legacy venue ---
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        configuration_legacy_federation = self.configuration_en_memoire(
            ["module_federation", "module_monnaie_locale"]
        )
        section = section_monnaies(configuration_legacy_federation)
        if section is None:
            constats_faux.append("legacy + fédération : section absente")
        else:
            if liens_de_la_section(section) != [adresse_assets_legacy]:
                constats_faux.append(
                    f"legacy + fédération : pages {liens_de_la_section(section)}"
                )
            titre_attendu = str(dashboard.MODULE_FIELDS["module_monnaie_locale"]["name"])
            if str(section.get("title")) != titre_attendu:
                constats_faux.append(
                    f"legacy + fédération : titre « {section.get('title')} »"
                )

        configuration_legacy_sans_federation = self.configuration_en_memoire([])
        with self.un_asset_legacy_le_temps_du_bloc("invite"):
            section = section_monnaies(configuration_legacy_sans_federation)
        if section is None:
            constats_faux.append("legacy invité, sans fédération : section absente")
        elif liens_de_la_section(section) != [adresse_assets_legacy]:
            constats_faux.append(
                f"legacy invité, sans fédération : pages {liens_de_la_section(section)}"
            )

        section = section_monnaies(
            self.configuration_en_memoire(["module_monnaie_locale"])
        )
        if section is not None:
            constats_faux.append("legacy sans fédération ni asset : section présente")

        assert constats_faux == [], "\n".join(constats_faux)

    def test_page_de_module_monnaies_sans_onglet_vide_en_legacy(self):
        """
        La page de module « Monnaies » d'un lieu legacy avec la fédération répond, et ne
        montre que l'onglet « Gérer » : un onglet sans page n'apparaît pas. Sans
        fédération ni asset legacy, elle n'existe pas (404). Par le client HTTP du lieu,
        connecté comme gestionnaire.
        / Legacy "Currencies" module page: only the "Manage" tab; 404 without access.
        """
        administrateur_du_lieu = TibilletUser.objects.create(
            email=f"admin-affichage-{uuid.uuid4().hex[:12]}@tibillet.localhost",
            username=f"admin-affichage-{uuid.uuid4().hex[:12]}",
            espece=TibilletUser.TYPE_HUM,
            is_staff=True,
            is_active=True,
        )
        administrateur_du_lieu.client_admin.add(self.tenant)
        navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        navigateur.force_login(administrateur_du_lieu)
        adresse_de_la_page = reverse(
            "staff_admin:page_de_module", args=[SLUG_DE_LA_SECTION_MONNAIES]
        )

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)

        configuration_avec_federation = self.configuration_en_memoire(
            ["module_federation", "module_monnaie_locale"]
        )
        with patch.object(
            Configuration, "get_solo", return_value=configuration_avec_federation
        ):
            with patch.object(Configuration, "save", autospec=True):
                reponse = navigateur.get(adresse_de_la_page)
        assert reponse.status_code == 200
        contenu = reponse.content.decode()
        assert 'data-testid="module-tab-gerer"' in contenu
        assert 'data-testid="module-tab-configurer"' not in contenu
        assert 'data-testid="module-tab-analyser"' not in contenu
        assert adresse_des_assets_legacy() in contenu

        configuration_sans_federation = self.configuration_en_memoire(
            ["module_monnaie_locale"]
        )
        with patch.object(
            Configuration, "get_solo", return_value=configuration_sans_federation
        ):
            with patch.object(Configuration, "save", autospec=True):
                reponse = navigateur.get(adresse_de_la_page)
        assert reponse.status_code == 404

    # ------------------------------------------------------------------ #
    #  21 — « Assets » sort du module Fédération                          #
    # ------------------------------------------------------------------ #

    def test_assets_absent_du_module_federation(self):
        """
        La section « Fédération et agenda participatif » ne contient plus les assets
        legacy (ils vivent dans « Monnaies ») ; elle garde ses options et ses espaces.
        Vrai pour un lieu v2 comme pour un lieu legacy, avec un asset legacy du lieu.
        / The Federation section no longer lists the legacy assets.
        """
        configuration = self.configuration_en_memoire(
            ["module_federation", "module_monnaie_locale"]
        )
        constats_faux = []

        for moteur in [MOTEUR_V2, MOTEUR_LEGACY]:
            self.poser_le_moteur_du_lieu_dedie(moteur)
            with self.un_asset_legacy_le_temps_du_bloc("origine"):
                sections, _toutes = self.sections_par_slug(configuration)
            section_federation = sections.get(SLUG_DE_LA_SECTION_FEDERATION)
            if section_federation is None:
                constats_faux.append(f"{moteur} : section Fédération absente")
                continue
            liens = liens_de_la_section(section_federation)
            if adresse_des_assets_legacy() in liens:
                constats_faux.append(f"{moteur} : « Assets » encore dans Fédération")
            for nom_de_la_page in [
                "staff_admin:BaseBillet_federationconfiguration_changelist",
                "staff_admin:BaseBillet_federatedplace_changelist",
            ]:
                if reverse(nom_de_la_page) not in liens:
                    constats_faux.append(f"{moteur} : {nom_de_la_page} absent")

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  22 — Invariant du rail : une page, une section                     #
    # ------------------------------------------------------------------ #

    def test_une_page_une_section_sur_un_lieu_v2_avec_assets_legacy(self):
        """
        Lieu v2, tous les modules allumés, un asset legacy fédéré : aucune page d'admin
        n'est rangée dans deux sections (même règle que
        `test_admin_fil_ariane_et_rail.py::test_aucune_page_n_appartient_a_deux_modules`),
        et sur la liste des assets legacy le rail ne surligne qu'une entrée : la section
        « Monnaies ».
        / v2 venue with a legacy asset: one page, one section; one highlighted entry.
        """
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration = self.configuration_en_memoire(TOUS_LES_DRAPEAUX_DE_MODULE)

        # Deux constructions du menu : le regroupement du rail modifie les sections
        # qu'il reçoit. / Built twice: grouping the rail mutates its input.
        with self.un_asset_legacy_le_temps_du_bloc("federe"):
            sections_pour_les_doublons, toutes_les_sections = self.sections_par_slug(
                configuration
            )
            _par_slug_du_rail, sections_pour_le_rail = self.sections_par_slug(
                configuration
            )

        proprietaire_de_la_page = {}
        doublons = []
        for section in toutes_les_sections:
            for lien in liens_de_la_section(section):
                if not lien.startswith("/admin/"):
                    continue
                if lien in proprietaire_de_la_page:
                    doublons.append(
                        (lien, proprietaire_de_la_page[lien], str(section.get("title")))
                    )
                proprietaire_de_la_page[lien] = str(section.get("title"))
        assert doublons == [], f"Pages rangées dans deux sections : {doublons}"

        assert SLUG_DE_LA_SECTION_MONNAIES in sections_pour_les_doublons
        titre_de_la_section_monnaies = str(
            sections_pour_les_doublons[SLUG_DE_LA_SECTION_MONNAIES]["title"]
        )
        assert adresse_des_assets_legacy() in liens_de_la_section(
            sections_pour_les_doublons[SLUG_DE_LA_SECTION_MONNAIES]
        )

        groupes_du_rail = dashboard._regrouper_sections_par_domaine(
            sections_pour_le_rail, chemin_courant=adresse_des_assets_legacy()
        )
        entrees_surlignees = []
        for groupe in groupes_du_rail:
            for entree in groupe.get("items", []):
                if entree.get("active"):
                    entrees_surlignees.append(str(entree.get("title")))
        assert entrees_surlignees == [titre_de_la_section_monnaies], entrees_surlignees

    # ------------------------------------------------------------------ #
    #  26 — Une carte fermée n'a pas d'encart BETA (M2)                   #
    # ------------------------------------------------------------------ #

    def test_carte_fermee_sans_encart_beta(self):
        """
        Tous les modules éteints. Les modules V2 en accès anticipé (BETA) ont un encart
        BETA sur leur carte : la caisse (carte `pos`) et la tireuse (carte générique).
        - lieu legacy : leurs cartes sont fermées par le verrou ; aucune des 4 cartes V2
          n'a d'encart BETA (ni `carte["beta"]`, ni le bloc dans le HTML) ;
        - lieu v2 (témoin) : la caisse et la tireuse gardent leur encart BETA.
        / Legacy: no BETA notice on a closed card; v2: POS and tap keep theirs.
        """
        cartes_beta_en_v2 = ["module_caisse", "module_tireuse"]
        constats_faux = []

        def encart_beta_dans_le_html(carte):
            marqueur_de_l_encart = f'data-testid="{carte["testid"]}-beta-notice"'
            return marqueur_de_l_encart in self.html_de_la_carte(carte)

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        cartes = self.cartes_par_module(self.configuration_en_memoire([]))
        for nom_du_module in DRAPEAUX_DES_MODULES_V2:
            carte = cartes[nom_du_module]
            if carte.get("moteur_legacy") is not True:
                constats_faux.append(f"legacy, {nom_du_module} : carte pas fermée")
            if carte.get("beta"):
                constats_faux.append(f"legacy, {nom_du_module} : carte[beta] vrai")
            if encart_beta_dans_le_html(carte):
                constats_faux.append(f"legacy, {nom_du_module} : encart BETA affiché")

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        cartes = self.cartes_par_module(self.configuration_en_memoire([]))
        for nom_du_module in cartes_beta_en_v2:
            if not encart_beta_dans_le_html(cartes[nom_du_module]):
                constats_faux.append(f"v2, {nom_du_module} : encart BETA absent")

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  27 — Le total d'un domaine compte les cartes fermées (M3)          #
    # ------------------------------------------------------------------ #

    def test_total_du_domaine_compte_les_cartes_fermees(self):
        """
        Tous les modules éteints, lu dans le contexte du tableau de bord
        (`dashboard_callback`) :
        - lieu legacy : le domaine Laboutik (la caisse) et le domaine Lémachines (kiosk,
          tireuse) affichent 0 / N, N = leurs cartes réelles (hors « bientôt
          disponible »), comme en v2 : ces modules existent, même fermés ;
        - la pastille « Découvrir plus de modules » compte toujours 4 de moins en legacy
          qu'en v2 (les 4 cartes fermées ne s'allument pas).
        / Legacy: domain counters show 0/N (real cards); the "discover" pill still skips
        the 4 closed cards.
        """
        configuration = self.configuration_en_memoire([])

        def contexte_du_tableau_de_bord():
            requete = RequestFactory().get("/admin/")
            with patch.object(Configuration, "get_solo", return_value=configuration):
                return dashboard.dashboard_callback(requete, {})

        def groupes_par_cle(contexte):
            groupes_trouves = {}
            for groupe in contexte["groupes_de_domaines"]:
                groupes_trouves[groupe["cle"]] = groupe
            return groupes_trouves

        def nombre_de_cartes_reelles(groupe):
            nombre = 0
            for carte in groupe["cartes"]:
                if carte.get("type") != "coming_soon":
                    nombre += 1
            return nombre

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        contexte_v2 = contexte_du_tableau_de_bord()
        self.poser_le_moteur_du_lieu_dedie(MOTEUR_LEGACY)
        contexte_legacy = contexte_du_tableau_de_bord()

        constats_faux = []
        groupes_legacy = groupes_par_cle(contexte_legacy)
        for cle_du_domaine in ["laboutik", "lemachines"]:
            groupe = groupes_legacy[cle_du_domaine]
            total_attendu = nombre_de_cartes_reelles(groupe)
            if total_attendu == 0:
                constats_faux.append(f"legacy, {cle_du_domaine} : aucune carte réelle")
            if groupe["total"] != total_attendu:
                constats_faux.append(
                    f"legacy, {cle_du_domaine} : total {groupe['total']} "
                    f"(attendu {total_attendu})"
                )
            if groupe["actifs"] != 0:
                constats_faux.append(
                    f"legacy, {cle_du_domaine} : actifs {groupe['actifs']} (attendu 0)"
                )

        ecart_de_la_pastille = (
            contexte_v2["modules_eteints"] - contexte_legacy["modules_eteints"]
        )
        if ecart_de_la_pastille != 4:
            constats_faux.append(
                f"pastille « Découvrir » : v2 {contexte_v2['modules_eteints']}, "
                f"legacy {contexte_legacy['modules_eteints']} (écart attendu 4)"
            )

        assert constats_faux == [], "\n".join(constats_faux)

    # ------------------------------------------------------------------ #
    #  28 — Les assets legacy sont lus une fois par requête (M4)          #
    # ------------------------------------------------------------------ #

    def test_assets_legacy_lus_une_fois_par_requete(self):
        """
        Le tableau de bord de l'admin d'un lieu v2 (monnaie locale allumée), par le client
        HTTP du lieu, connecté comme gestionnaire : le menu latéral, les onglets et le
        rail construisent les sections plusieurs fois par page, mais la requête « le lieu
        a des assets legacy » (table `fedow_public_assetfedowpublic`) n'est faite qu'une
        fois. On compte les requêtes SQL de la page qui lisent cette table.
        / One admin page: the "has legacy assets" query runs once, not once per build.
        """
        administrateur_du_lieu = TibilletUser.objects.create(
            email=f"admin-requetes-{uuid.uuid4().hex[:12]}@tibillet.localhost",
            username=f"admin-requetes-{uuid.uuid4().hex[:12]}",
            espece=TibilletUser.TYPE_HUM,
            is_staff=True,
            is_active=True,
        )
        administrateur_du_lieu.client_admin.add(self.tenant)
        navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        navigateur.force_login(administrateur_du_lieu)

        self.poser_le_moteur_du_lieu_dedie(MOTEUR_V2)
        configuration = self.configuration_en_memoire(["module_monnaie_locale"])

        with patch.object(Configuration, "get_solo", return_value=configuration):
            with patch.object(Configuration, "save", autospec=True):
                with CaptureQueriesContext(connection) as requetes_de_la_page:
                    reponse = navigateur.get(reverse("staff_admin:index"))
        assert reponse.status_code == 200

        requetes_des_assets_legacy = []
        for requete in requetes_de_la_page.captured_queries:
            if "fedow_public_assetfedowpublic" in requete["sql"]:
                requetes_des_assets_legacy.append(requete["sql"])

        assert len(requetes_des_assets_legacy) == 1, (
            f"{len(requetes_des_assets_legacy)} requêtes sur les assets legacy :\n"
            + "\n".join(requetes_des_assets_legacy)
        )
