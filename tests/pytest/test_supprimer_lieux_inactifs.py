"""
Supprimer les lieux qui n'ont jamais eu aucune activité, avant la migration de la bascule.
/ Delete the venues that never had any activity, before the switch-over migration.

LOCALISATION : tests/pytest/test_supprimer_lieux_inactifs.py

RÈGLE MÉTIER TESTÉE
Fiche : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md §18 (et §12 étape 2 bis),
brief : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-R-N.md.
- `manage.py supprimer_lieux_inactifs` est À BLANC par défaut : il n'écrit rien.
- `--executer` supprime ; `--liste <fichier>` (un domaine par ligne) est alors obligatoire.
  Un lieu n'est supprimé que s'il est dans la liste ET encore inactif. Un lieu de la liste
  redevenu actif est gardé et signalé (« dans la liste, mais actif maintenant : <raisons> »).
- Un lieu est inactif si les 8 critères du tableau §18 sont vrais. Sinon il est gardé, avec
  toutes ses raisons.
- Critère 5 : un groupe de ressources garde le lieu (aucune migration n'en sème).
- Critère 5 : la page d'accueil par défaut que la migration `BaseBillet 0225` crée dans
  chaque lieu (1 page d'accueil, au plus 3 blocs, aucune image) est tolérée ; une ligne de
  plus garde le lieu (« table non vide : pages_… »).
- Une transaction par lieu : schéma supprimé, utilisateurs et portefeuilles GARDÉS (leurs
  liens vers le lieu sont vidés), fiche d'onboarding supprimée, domaines et `Client`
  supprimés. Une référence oubliée vers le lieu annule la transaction : le schéma revient.
- Le lieu est toujours désigné par son domaine principal, jamais par son schéma.
- Un mail par administrateur, qui liste ses lieux supprimés, mis en file Celery après le
  COMMIT ; aucun mail à blanc, avec `--sans-mail`, ni si la transaction est annulée.
/ Business rules: dry run by default; `--executer` needs `--liste`; 8 criteria; one
transaction per venue; users and wallets kept; venue named by its primary domain; one mail
per admin, queued after COMMIT only.

CONTRAT (précisé par l'orchestrateur le 2026-10-07 ; les valeurs sont regroupées dans les
constantes plus bas pour être changées en un seul endroit)
- La commande s'appelle par `call_command("supprimer_lieux_inactifs", ...)`. Une erreur
  d'options lève `CommandError`.
- `--liste` limite l'examen aux lieux de la liste, à blanc comme en exécution.
- `--rapport <chemin.csv>` : un seul fichier CSV (UTF-8, séparateur virgule, une ligne
  d'en-tête), une ligne par lieu, avec les colonnes `liste`, `domaine`, `date_de_creation`
  (AAAA-MM-JJ) et `raisons`. `liste` vaut « à supprimer » (à blanc), « supprimé »
  (`--executer`), « gardé » ou « échec » (raison = le message de l'erreur).
- La raison d'un lieu supprimé contient « aucune activité ». Chaque raison d'un lieu gardé
  commence par le libellé de son critère, suivi d'une précision lisible (ex. « activité
  dans le lieu : événements (2) ») : les tests ne vérifient que le libellé
  (constante `LIBELLE_DU_CRITERE`).
- Une ligne d'une table (publique ou d'un autre lieu) qui pointe vers le lieu, hors des
  tables que l'outil sait nettoyer, garde le lieu dès la détection : raison « référence
  inconnue : <table> ».
- Un lieu sans domaine principal (emplacement du pool) n'apparaît dans aucune liste ; le
  résumé chiffré dit « N emplacements du pool ignorés ». Un lieu du pool AVEC un domaine
  est « gardé », raison catégorie.
- `--traces-externes <chemin.csv>` : colonnes `domaine`, `stripe_connect`,
  `stripe_connect_test`, `place_fedow`, `administrateurs` (adresses séparées par « ; »).
  Le résumé compte « N lieux supprimés sans administrateur (aucun mail) ».
- Chaque suppression réussie est notée après son COMMIT. Une fois tous les lieux traités,
  les mails sont mis en file : une tâche Celery demandée par `.delay()` (donc
  `Task.apply_async`), un mail par administrateur, qui liste ses lieux supprimés. Exécutée
  avec ses arguments, la tâche envoie le mail par le mécanisme du projet
  (`CeleryMailerClass`) ; objet « Votre espace TiBillet a été fermé ». Rien pour un lieu
  en échec.
/ Contract: CSV columns and values, reason labels, unknown references keep the venue, pool
slots ignored, external traces columns, mails queued once all venues are processed.

SIMULATIONS
- AUCUN marqueur `django_db` : la commande ouvre ses propres transactions et les valide
  (COMMIT) ; c'est ce qu'on veut prouver (schéma qui revient après une annulation, mail
  demandé après le COMMIT). Il n'y a donc pas d'annulation automatique en fin de test.
- Chaque lieu est un lieu JETABLE `test_nettoyage_*`, créé par le test : schéma copié du
  schéma modèle `test_modele` (tests/pytest/schemas_clones.py, comme le conftest), ligne
  `Client` et domaine principal écrits par `bulk_create()` (aucun `save()` : pas de
  migrations rejouées, pas de signal). Jamais `lespass` ni un lieu de démo.
- Tout ce que le test crée est noté dans un registre. La fixture `registre` le supprime en
  fin de test, même en échec, en SQL brut (tests/PIEGES.md 12.5 : `Client.delete()` ne
  marche pas). Garde-fou : seuls les schémas et les tables qui commencent par
  `test_nettoyage_` sont supprimés.
- Chaque lancement passe `--liste` avec les seuls domaines de lieux jetables : la commande
  ne peut examiner ni supprimer aucun autre lieu de la base de dev. Trois tests s'en
  passent, parce qu'ils prouvent autre chose : le passage à blanc complet (test 1), le
  refus de `--executer` sans `--liste` (test 6), l'emplacement du pool ignoré (test 14).
  Aucun des trois n'écrit en base si la commande est correcte.
- Les tâches Celery sont interceptées (`Task.apply_async` remplacé) : rien ne part au
  worker. Le test qui lit le mail exécute la tâche lui-même ; le mail est lu dans
  `mailoutbox` (pytest-django).
- Les lignes du lieu (événement, produit, configuration…) sont écrites par `bulk_create()`
  dans `tenant_context(lieu)` : aucun signal, aucun appel à Fedow ni à Stripe, rien dans
  memcached.
/ No django_db: the command commits. Disposable cloned venues, deleted at teardown in raw
SQL. Celery intercepted. Tenant rows written by bulk_create().

Lancer / Run : make test ARGS="tests/pytest/test_supprimer_lieux_inactifs.py"
"""

import csv
import os
import uuid
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone, translation
from django_tenants.utils import get_public_schema_name, schema_exists, tenant_context

import schemas_clones
from AuthBillet.models import TibilletUser, Wallet
from booking.models import ResourceGroup
from BaseBillet.models import (
    BrevoConfig,
    Configuration,
    Event,
    FederatedPlace,
    FormbricksConfig,
    GhostConfig,
    LigneArticle,
    Membership,
    Paiement_stripe,
    PostalAddress,
    Price,
    Product,
    Tag,
    Tva,
)
from Customers.models import Client, Domain
from fabriques_vente import creer_tarif_vendu
from fedow_connect.models import FedowConfig
from fedow_public.models import AssetFedowPublic
from MetaBillet.models import WaitingConfiguration
from pages.models import Bloc, Page
from pages.services import construire_page_accueil
from QrcodeCashless.models import Detail

# --------------------------------------------------------------------------
# Constantes : la commande et son contrat
# / Constants: the command and its contract
# --------------------------------------------------------------------------

NOM_DE_LA_COMMANDE = "supprimer_lieux_inactifs"

# Préfixe de tout ce que ces tests créent et suppriment (schémas, tables, noms).
# Le nettoyage refuse de toucher à un nom qui ne commence pas par ce préfixe.
# / Prefix of everything these tests create and delete. Cleanup refuses any other name.
PREFIXE_DES_LIEUX_JETABLES = "test_nettoyage_"

# Un lieu jetable a « toujours » plus de 60 jours (défaut de `--jours-minimum`).
# / A disposable venue is older than the 60-day default.
AGE_D_UN_LIEU_ANCIEN_EN_JOURS = 365
AGE_D_UN_LIEU_RECENT_EN_JOURS = 10

# Colonnes et valeurs du rapport CSV (`--rapport`).
# / Columns and values of the CSV report.
COLONNE_LISTE = "liste"
COLONNE_DOMAINE = "domaine"
COLONNE_DATE_DE_CREATION = "date_de_creation"
COLONNE_RAISONS = "raisons"
LISTE_A_SUPPRIMER = "à supprimer"
LISTE_SUPPRIME = "supprimé"
LISTE_GARDE = "gardé"
LISTE_ECHEC = "échec"
RAISON_D_UN_LIEU_SUPPRIME = "aucune activité"
RAISON_REFERENCE_INCONNUE = "référence inconnue"

# Phrase du résumé chiffré pour les emplacements du pool (lieux sans domaine principal).
# / Summary sentence for pool slots (venues without a primary domain).
PHRASE_EMPLACEMENTS_DU_POOL_IGNORES = "emplacements du pool ignorés"

# Colonnes du CSV des traces externes (`--traces-externes`).
# / Columns of the external traces CSV.
COLONNE_STRIPE_CONNECT = "stripe_connect"
COLONNE_STRIPE_CONNECT_TEST = "stripe_connect_test"
COLONNE_PLACE_FEDOW = "place_fedow"
COLONNE_ADMINISTRATEURS = "administrateurs"

# Le libellé de chaque critère du tableau §18, tel qu'il doit apparaître (sans tenir compte
# des majuscules) dans les raisons d'un lieu gardé, avant la précision. Aucun ne contient
# un autre.
# / Label of each §18 criterion, as it must appear in a kept venue's reasons.
LIBELLE_DU_CRITERE = {
    1: "catégorie",
    2: "créé il y a moins de",
    3: "activité dans le lieu",
    4: "catalogue",
    5: "table non vide",
    6: "configuration personnalisée",
    7: "trace dans les tables partagées",
    8: "cité par un autre lieu",
}

# Phrase de la fiche pour un lieu de la liste redevenu actif.
# / Sentence of the spec for a listed venue that became active.
PHRASE_LIEU_DE_LA_LISTE_REDEVENU_ACTIF = "dans la liste, mais actif maintenant"

# Objet du mail aux administrateurs (fiche §18, texte tel quel).
# / Subject of the mail to the admins (spec §18, verbatim).
OBJET_DU_MAIL = "Votre espace TiBillet a été fermé"


# --------------------------------------------------------------------------
# Registre et nettoyage de tout ce que le test crée
# / Registry and cleanup of everything the test creates
# --------------------------------------------------------------------------


class RegistreDesObjetsCrees:
    """
    Liste de tout ce qu'un test crée et qui doit disparaître à la fin.
    / List of everything a test creates and that must disappear at the end.

    Chaque objet est noté AVANT d'être créé quand c'est possible (un schéma à moitié copié
    est quand même supprimé).
    / Each object is recorded BEFORE creation when possible.
    """

    def __init__(self):
        self.schemas_des_lieux = []
        self.tables_publiques_de_test = []
        self.uuids_des_monnaies = []
        self.pks_des_cartes = []
        self.uuids_des_fiches_d_onboarding = []
        self.pks_des_utilisateurs = []
        self.uuids_des_portefeuilles = []


def verifier_le_prefixe(nom):
    """
    Refuse tout nom qui ne commence pas par le préfixe des lieux jetables.
    / Refuses any name that does not start with the disposable prefix.
    """
    if not nom.startswith(PREFIXE_DES_LIEUX_JETABLES):
        raise RuntimeError(
            f"Nettoyage refusé : « {nom} » ne commence pas par {PREFIXE_DES_LIEUX_JETABLES}"
        )


def supprimer_des_lignes_du_schema_public(
    nom_de_la_table, nom_de_la_cle, valeurs_de_la_cle
):
    """
    Supprime des lignes d'une table du schéma public, et d'abord les lignes du schéma
    public qui pointent vers elles (liens plusieurs-à-plusieurs, domaines, fiches…).
    / Deletes rows of a public table, after the public rows pointing to them.

    Les tables qui pointent vers `nom_de_la_table` sont lues dans le catalogue PostgreSQL
    (`pg_constraint`), comme la purge de tests/PIEGES.md 12.5.bis. Un seul niveau : les
    lignes supprimées en premier ne doivent être la cible d'aucune autre ligne.
    / Pointing tables are read from the catalogue. One level only.
    """
    if not valeurs_de_la_cle:
        return

    # Les valeurs sont comparées en texte : un uuid comme un entier.
    # / Values are compared as text: uuid or integer alike.
    valeurs_en_texte = []
    for valeur in valeurs_de_la_cle:
        valeurs_en_texte.append(str(valeur))

    with connection.cursor() as curseur:
        # Lit les clés étrangères des tables du schéma public qui visent cette table :
        # le nom de la table qui pointe et le nom de sa colonne.
        # / Reads the foreign keys of public tables that target this table.
        curseur.execute(
            """
            SELECT table_qui_pointe.relname, colonne_qui_pointe.attname
            FROM pg_constraint contrainte
            JOIN pg_class table_qui_pointe ON table_qui_pointe.oid = contrainte.conrelid
            JOIN pg_namespace espace ON espace.oid = table_qui_pointe.relnamespace
            JOIN pg_attribute colonne_qui_pointe
                ON colonne_qui_pointe.attrelid = contrainte.conrelid
                AND colonne_qui_pointe.attnum = contrainte.conkey[1]
            WHERE contrainte.contype = 'f'
              AND contrainte.confrelid = %s::regclass
              AND espace.nspname = 'public'
            """,
            [f'public."{nom_de_la_table}"'],
        )
        references_vers_la_table = curseur.fetchall()

        # Supprime les lignes qui pointent vers les lignes à supprimer.
        # / Deletes the rows pointing to the rows to delete.
        for table_qui_pointe, colonne_qui_pointe in references_vers_la_table:
            curseur.execute(
                f'DELETE FROM public."{table_qui_pointe}" '
                f'WHERE "{colonne_qui_pointe}"::text = ANY(%s)',
                [valeurs_en_texte],
            )

        # Supprime les lignes elles-mêmes.
        # / Deletes the rows themselves.
        curseur.execute(
            f'DELETE FROM public."{nom_de_la_table}" WHERE "{nom_de_la_cle}"::text = ANY(%s)',
            [valeurs_en_texte],
        )


def nettoyer_tout_ce_que_le_test_a_cree(registre):
    """
    Supprime tout ce que le registre a noté, en SQL brut, dans un ordre qui respecte les
    clés étrangères.
    / Deletes everything the registry recorded, in raw SQL, in foreign-key order.

    ORDRE :
    1. les tables publiques de test (elles pointent vers des lieux) ;
    2. les schémas des lieux (ils contiennent les `FederatedPlace` qui citent un lieu) ;
    3. dans une transaction : monnaies, cartes, fiches d'onboarding, utilisateurs,
       portefeuilles, puis les lignes `Client` encore là (avec leurs domaines).
    `DROP ... IF EXISTS` : la commande a peut-être déjà supprimé le lieu.
    / Order: test tables, venue schemas, then public rows in one transaction.
    """
    connection.set_schema_to_public()

    with connection.cursor() as curseur:
        for nom_de_la_table in registre.tables_publiques_de_test:
            verifier_le_prefixe(nom_de_la_table)
            curseur.execute(f'DROP TABLE IF EXISTS public."{nom_de_la_table}"')

        for nom_du_schema in registre.schemas_des_lieux:
            verifier_le_prefixe(nom_du_schema)
            curseur.execute(f'DROP SCHEMA IF EXISTS "{nom_du_schema}" CASCADE')

    with transaction.atomic():
        supprimer_des_lignes_du_schema_public(
            "fedow_public_assetfedowpublic", "uuid", registre.uuids_des_monnaies
        )
        supprimer_des_lignes_du_schema_public(
            "QrcodeCashless_detail", "id", registre.pks_des_cartes
        )
        supprimer_des_lignes_du_schema_public(
            "MetaBillet_waitingconfiguration",
            "uuid",
            registre.uuids_des_fiches_d_onboarding,
        )
        supprimer_des_lignes_du_schema_public(
            "AuthBillet_tibilletuser", "id", registre.pks_des_utilisateurs
        )
        supprimer_des_lignes_du_schema_public(
            "AuthBillet_wallet", "uuid", registre.uuids_des_portefeuilles
        )

        # Les lignes `Client` des lieux jetables encore présentes (la commande ne les a pas
        # supprimées, ou le test a échoué avant).
        # / Disposable Client rows still present.
        with connection.cursor() as curseur:
            curseur.execute(
                'SELECT uuid FROM "Customers_client" WHERE schema_name = ANY(%s)',
                [registre.schemas_des_lieux],
            )
            uuids_des_lieux_encore_presents = []
            for (uuid_du_lieu,) in curseur.fetchall():
                uuids_des_lieux_encore_presents.append(uuid_du_lieu)

        supprimer_des_lignes_du_schema_public(
            "Customers_client", "uuid", uuids_des_lieux_encore_presents
        )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def schema_modele_a_jour():
    """
    Garde-fou, puis schéma modèle `test_modele` prêt (refait par les migrations s'il est
    périmé, ~1 min, une seule fois).
    / Safety check, then the template schema is ready.

    Ces tests suppriment des schémas : ils ne tournent qu'avec DEBUG=1 et TEST=1.
    On lit l'ENVIRONNEMENT du conteneur, comme TiBillet/settings.py, jamais
    `settings.DEBUG` : pytest-django force `settings.DEBUG` à False pendant les tests,
    la garde refuserait alors toujours.
    / These tests drop schemas: DEBUG=1 and TEST=1 only. Read from the environment,
    never settings.DEBUG: pytest-django forces it to False during tests.
    """
    debug_actif_dans_le_conteneur = os.environ.get("DEBUG") == "1"
    test_actif_dans_le_conteneur = os.environ.get("TEST") == "1"
    if not (debug_actif_dans_le_conteneur and test_actif_dans_le_conteneur):
        pytest.fail(
            "Ces tests suppriment des schémas : DEBUG=1 et TEST=1 obligatoires."
        )
    schemas_clones.preparer_le_schema_modele()
    yield


@pytest.fixture
def registre():
    """
    Le registre du test. En fin de test, même en échec, tout ce qu'il a noté est supprimé.
    / The test registry. Everything recorded is deleted at the end, even on failure.
    """
    connection.set_schema_to_public()
    registre_du_test = RegistreDesObjetsCrees()
    try:
        yield registre_du_test
    finally:
        nettoyer_tout_ce_que_le_test_a_cree(registre_du_test)


# --------------------------------------------------------------------------
# Création d'un lieu jetable
# / Creating a disposable venue
# --------------------------------------------------------------------------


def remplir_comme_l_onboarding(lieu):
    """
    Écrit dans le lieu ce que le formulaire de création y laisse : la configuration
    (nom, slug, email, description, téléphone, site), une adresse, et un produit de
    réservation gratuite avec un tarif à 0. Rien de tout cela ne rend le lieu actif
    (critères 4 et 6 du §18).
    / Writes what the creation form leaves: configuration, one address, one free booking
    product with a 0 price. None of it makes the venue active.

    `bulk_create()` : pas de `save()`, donc rien dans memcached (tests/PIEGES.md 13.22).
    """
    with tenant_context(lieu.client):
        adresse_du_lieu = PostalAddress(
            name=lieu.nom,
            street_address="1 rue du Test",
            address_locality="Saint-Denis",
            postal_code="97400",
            address_country="FR",
        )
        PostalAddress.objects.bulk_create([adresse_du_lieu])

        Configuration.objects.bulk_create(
            [
                Configuration(
                    pk=Configuration.singleton_instance_id,
                    organisation=lieu.nom,
                    slug=lieu.domaine.split(".")[0],
                    email=f"contact@{lieu.domaine}",
                    short_description="Un lieu de test, jamais utilisé.",
                    phone="0262000000",
                    site_web=f"https://{lieu.domaine}",
                    postal_address=adresse_du_lieu,
                )
            ]
        )

        produit_de_reservation_gratuite = Product(
            name="Réservation gratuite",
            categorie_article=Product.FREERES,
        )
        Product.objects.bulk_create([produit_de_reservation_gratuite])
        Price.objects.bulk_create(
            [
                Price(
                    product=produit_de_reservation_gratuite,
                    name="Gratuit",
                    prix=Decimal("0.00"),
                )
            ]
        )
    connection.set_schema_to_public()


def creer_un_lieu_jetable(
    registre,
    suffixe,
    age_en_jours=AGE_D_UN_LIEU_ANCIEN_EN_JOURS,
    avec_domaine_principal=True,
):
    """
    Crée un lieu jetable, tel que l'onboarding le laisse, sans aucune activité.
    / Creates a disposable venue, as onboarding leaves it, with no activity.

    FLUX :
    1. noter le schéma dans le registre (il sera supprimé même si la suite échoue) ;
    2. copier le schéma modèle (`schemas_clones`, comme le conftest) : un lieu neuf, migré ;
    3. écrire la ligne `Client` et son domaine principal par `bulk_create()` : pas de
       `save()`, donc pas de migrations rejouées ni de signal ;
    4. poser la date de création (`created_on` se remplit seul à aujourd'hui) ;
    5. remplir le lieu comme l'onboarding.
    / Flow: record, clone the template, bulk_create Client + primary domain, set the
    creation date, fill like onboarding.

    :param suffixe: mot court qui rend le lieu lisible dans les messages (ex. "liste")
    :param age_en_jours: âge du lieu
    :param avec_domaine_principal: False pour un emplacement du pool sans domaine (le nom
        de domaine est alors calculé mais jamais écrit en base)
    :return: SimpleNamespace(client, nom_du_schema, domaine, nom, date_de_creation)
    """
    identifiant = uuid.uuid4().hex[:8]
    nom_du_schema = f"{PREFIXE_DES_LIEUX_JETABLES}{suffixe}_{identifiant}"
    # Le domaine prend des tirets, le schéma des soulignés : un schéma recopié par erreur
    # dans un rapport se voit.
    # / Hyphens in the domain, underscores in the schema: a leaked schema name shows.
    domaine = f"test-nettoyage-{suffixe}-{identifiant}.tibillet.localhost"
    nom_du_lieu = f"Test nettoyage {suffixe} {identifiant}"

    registre.schemas_des_lieux.append(nom_du_schema)
    schemas_clones.creer_le_schema_par_clonage(nom_du_schema)

    client_du_lieu = Client(
        schema_name=nom_du_schema,
        name=nom_du_lieu,
        categorie=Client.SALLE_SPECTACLE,
    )
    Client.objects.bulk_create([client_du_lieu])
    if avec_domaine_principal:
        Domain.objects.bulk_create(
            [Domain(domain=domaine, tenant=client_du_lieu, is_primary=True)]
        )

    date_de_creation = timezone.localdate() - timedelta(days=age_en_jours)
    Client.objects.filter(pk=client_du_lieu.pk).update(created_on=date_de_creation)

    lieu = SimpleNamespace(
        client=client_du_lieu,
        nom_du_schema=nom_du_schema,
        domaine=domaine,
        nom=nom_du_lieu,
        date_de_creation=date_de_creation,
    )
    remplir_comme_l_onboarding(lieu)
    return lieu


def creer_un_utilisateur(registre):
    """
    Crée un utilisateur de test (schéma public), email unique en minuscules.
    / Creates a test user (public schema), unique lowercase email.
    """
    email = f"test+nettoyage{uuid.uuid4().hex[:8]}@mock.test"
    utilisateur = TibilletUser.objects.create(
        email=email, username=email, is_active=True
    )
    registre.pks_des_utilisateurs.append(utilisateur.pk)
    return utilisateur


def creer_un_administrateur_des_lieux(registre, lieux):
    """
    Crée un utilisateur administrateur de chaque lieu donné (`client_admin`).
    / Creates a user who administers each given venue.
    """
    administrateur = creer_un_utilisateur(registre)
    for lieu in lieux:
        administrateur.client_admin.add(lieu.client)
    return administrateur


def creer_une_fiche_d_onboarding(registre, lieu):
    """
    La fiche d'onboarding du lieu (`WaitingConfiguration`, schéma public). Elle porte les
    coordonnées du demandeur.
    / The venue's onboarding record (public schema).
    """
    fiche_d_onboarding = WaitingConfiguration(
        organisation=lieu.nom,
        email=f"demandeur+{uuid.uuid4().hex[:8]}@mock.test",
        phone="0262000000",
        tenant=lieu.client,
    )
    WaitingConfiguration.objects.bulk_create([fiche_d_onboarding])
    registre.uuids_des_fiches_d_onboarding.append(fiche_d_onboarding.uuid)
    return fiche_d_onboarding


def creer_une_table_qui_pointe_vers_le_lieu(registre, lieu, nom_du_schema_de_la_table):
    """
    Crée une table que la commande ne connaît pas, avec une clé étrangère vers
    `Customers_client` (différée, comme celles de Django), et une ligne qui pointe vers le
    lieu. Aucun nettoyage de la commande ne la vide.
    / Creates a table unknown to the command, with a deferred foreign key to
    Customers_client, and one row pointing to the venue.

    :param nom_du_schema_de_la_table: le schéma public, ou le schéma d'un autre lieu
        jetable. Une table du schéma public est notée dans le registre ; celle d'un autre
        lieu part avec le schéma de ce lieu.
    / The public schema, or another disposable venue's schema.
    """
    nom_de_la_table = f"{PREFIXE_DES_LIEUX_JETABLES}reference_{uuid.uuid4().hex[:8]}"
    if nom_du_schema_de_la_table == get_public_schema_name():
        registre.tables_publiques_de_test.append(nom_de_la_table)
    else:
        verifier_le_prefixe(nom_du_schema_de_la_table)

    with connection.cursor() as curseur:
        curseur.execute(
            f'CREATE TABLE "{nom_du_schema_de_la_table}"."{nom_de_la_table}" ('
            f"  id serial PRIMARY KEY,"
            f'  lieu_id uuid NOT NULL REFERENCES public."Customers_client" (uuid)'
            f"    DEFERRABLE INITIALLY DEFERRED"
            f")"
        )
        curseur.execute(
            f'INSERT INTO "{nom_du_schema_de_la_table}"."{nom_de_la_table}" (lieu_id) '
            f"VALUES (%s)",
            [str(lieu.client.pk)],
        )
    return nom_de_la_table


# --------------------------------------------------------------------------
# Lancer la commande, lire ses rapports
# / Running the command, reading its reports
# --------------------------------------------------------------------------


@contextmanager
def taches_celery_interceptees(noms_des_schemas_a_surveiller):
    """
    Intercepte toutes les tâches Celery demandées, sans les envoyer au worker.
    / Intercepts every requested Celery task, without sending it to the worker.

    `.delay(...)` appelle `Task.apply_async(...)` : on le remplace sur la classe de base
    (même procédé que `fabriques_panier.taches_celery_enregistrees`). Pour chaque tâche,
    on note AU MOMENT de la demande : si la connexion est encore dans une transaction, et
    quels schémas surveillés existent encore. Après le COMMIT d'un lieu supprimé, son
    schéma n'existe plus.
    / Patches the base Task.apply_async. At request time, records whether the connection
    is still inside a transaction and which watched schemas still exist.
    """
    from celery.app.task import Task

    taches_demandees = []

    def enregistrer_la_tache(tache, args=None, kwargs=None, **options):
        schemas_encore_presents = []
        for nom_du_schema in noms_des_schemas_a_surveiller:
            if schema_exists(nom_du_schema):
                schemas_encore_presents.append(nom_du_schema)
        taches_demandees.append(
            SimpleNamespace(
                tache=tache,
                arguments=tuple(args or ()),
                arguments_nommes=dict(kwargs or {}),
                demandee_dans_une_transaction=connection.in_atomic_block,
                schemas_encore_presents=schemas_encore_presents,
            )
        )
        return MagicMock()

    with patch.object(
        Task, "apply_async", autospec=True, side_effect=enregistrer_la_tache
    ):
        yield taches_demandees


def lancer_la_commande(*options, schemas_a_surveiller=()):
    """
    Lance la commande avec ses options, tâches Celery interceptées.
    / Runs the command with its options, Celery tasks intercepted.

    Échoue tout de suite si la commande n'existe pas : sinon un test qui attend une
    `CommandError` passerait sur l'erreur « Unknown command ».
    / Fails right away if the command does not exist.

    :return: SimpleNamespace(sortie, taches_demandees)
    """
    if NOM_DE_LA_COMMANDE not in get_commands():
        pytest.fail(f"La commande « {NOM_DE_LA_COMMANDE} » n'existe pas.")

    connection.set_schema_to_public()
    sortie_standard = StringIO()
    sortie_d_erreur = StringIO()
    with taches_celery_interceptees(schemas_a_surveiller) as taches_demandees:
        call_command(
            NOM_DE_LA_COMMANDE,
            *options,
            stdout=sortie_standard,
            stderr=sortie_d_erreur,
        )
    connection.set_schema_to_public()
    return SimpleNamespace(
        sortie=sortie_standard.getvalue() + sortie_d_erreur.getvalue(),
        taches_demandees=taches_demandees,
    )


def ecrire_la_liste_des_domaines(tmp_path, lieux):
    """
    Écrit le fichier `--liste` : un domaine principal par ligne.
    / Writes the `--liste` file: one primary domain per line.
    """
    chemin_de_la_liste = tmp_path / f"domaines_valides_{uuid.uuid4().hex[:8]}.txt"
    lignes = []
    for lieu in lieux:
        lignes.append(lieu.domaine)
    chemin_de_la_liste.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return str(chemin_de_la_liste)


def lire_un_csv(chemin):
    """
    Lit un CSV écrit par la commande : (noms des colonnes, liste des lignes).
    `utf-8-sig` accepte aussi un fichier qui commence par une marque BOM.
    / Reads a CSV written by the command; utf-8-sig also accepts a BOM.
    """
    with open(chemin, encoding="utf-8-sig", newline="") as fichier:
        lecteur = csv.DictReader(fichier)
        lignes = []
        for ligne in lecteur:
            lignes.append(ligne)
        return list(lecteur.fieldnames or []), lignes


def ligne_du_lieu(lignes, lieu):
    """
    La ligne du CSV dont la colonne `domaine` est le domaine du lieu, ou None.
    / The CSV row of the venue (by domain), or None.
    """
    for ligne in lignes:
        if ligne.get(COLONNE_DOMAINE) == lieu.domaine:
            return ligne
    return None


def lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu):
    """
    Lance la commande à blanc, limitée au lieu par `--liste`, avec `--rapport`. Rend la
    ligne du lieu dans le rapport.
    / Dry run limited to the venue by --liste, with --rapport; returns the venue's row.
    """
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])
    chemin_du_rapport = str(tmp_path / f"rapport_{uuid.uuid4().hex[:8]}.csv")
    lancer_la_commande("--liste", chemin_de_la_liste, "--rapport", chemin_du_rapport)
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    return ligne_du_lieu(lignes, lieu)


def le_client_existe(lieu):
    return Client.objects.filter(pk=lieu.client.pk).exists()


def le_domaine_existe(lieu):
    return Domain.objects.filter(domain=lieu.domaine).exists()


def executer_les_taches_demandees(taches_demandees):
    """
    Exécute chaque tâche demandée, avec ses arguments, comme le ferait le worker
    (appel direct de `run`), en français.
    / Runs each requested task with its arguments, as the worker would, in French.
    """
    with translation.override("fr"):
        for tache_demandee in taches_demandees:
            tache_demandee.tache.run(
                *tache_demandee.arguments, **tache_demandee.arguments_nommes
            )


def texte_complet_du_mail(mail):
    """
    L'objet, le texte et la version HTML d'un mail, bout à bout.
    / Subject, text and HTML version of a mail, joined.
    """
    morceaux = [mail.subject, mail.body or ""]
    for contenu, _type_de_contenu in getattr(mail, "alternatives", []):
        morceaux.append(contenu)
    return "\n".join(morceaux)


# --------------------------------------------------------------------------
# Ce qui rend un lieu actif : une fonction par cas du test 4
# / What makes a venue active: one function per case of test 4
# --------------------------------------------------------------------------


def passer_le_lieu_en_categorie_pool(lieu, registre):
    """Critère 1 : un lieu du pool (`W`). M et R ne sont pas posés : du code lit LA ligne
    `ROOT` par `.get()` (fedow_connect/validators.py, onboard/views.py) et LA ligne `META`
    par `.first()` ; un second lieu R ou M, validé en base pendant le test, les tromperait.
    / Criterion 1: a pool venue (W). M and R are not set: code reads THE ROOT row with
    .get() and THE META row with .first()."""
    Client.objects.filter(pk=lieu.client.pk).update(categorie=Client.WAITING_CONFIG)


def rajeunir_le_lieu(lieu, registre):
    """Critère 2 : créé il y a 10 jours. / Criterion 2: created 10 days ago."""
    date_recente = timezone.localdate() - timedelta(days=AGE_D_UN_LIEU_RECENT_EN_JOURS)
    Client.objects.filter(pk=lieu.client.pk).update(created_on=date_recente)


def poser_un_evenement(lieu, registre):
    """Critère 3 : un événement. / Criterion 3: an event."""
    with tenant_context(lieu.client):
        Event.objects.bulk_create(
            [
                Event(
                    name="Concert du test", datetime=timezone.now() + timedelta(days=30)
                )
            ]
        )
    connection.set_schema_to_public()


def poser_une_ligne_de_vente(lieu, registre):
    """Critère 3 : une ligne de vente. / Criterion 3: a sale line."""
    with tenant_context(lieu.client):
        tarif_vendu = creer_tarif_vendu(nom="Nettoyage", prix_en_euros="5.00")
        LigneArticle.objects.bulk_create(
            [LigneArticle(pricesold=tarif_vendu, qty=Decimal("1"))]
        )
    connection.set_schema_to_public()


def poser_une_adhesion(lieu, registre):
    """Critère 3 : une adhésion. / Criterion 3: a membership."""
    with tenant_context(lieu.client):
        Membership.objects.bulk_create([Membership()])
    connection.set_schema_to_public()


def poser_un_paiement_stripe(lieu, registre):
    """Critère 3 : un paiement Stripe. / Criterion 3: a Stripe payment."""
    with tenant_context(lieu.client):
        Paiement_stripe.objects.bulk_create([Paiement_stripe()])
    connection.set_schema_to_public()


def poser_un_produit_d_adhesion(lieu, registre):
    """Critère 4 : un produit d'adhésion en plus du produit de l'onboarding.
    / Criterion 4: a membership product besides the onboarding one."""
    with tenant_context(lieu.client):
        Product.objects.bulk_create(
            [Product(name="Adhésion du test", categorie_article=Product.ADHESION)]
        )
    connection.set_schema_to_public()


def poser_un_prix_non_nul(lieu, registre):
    """Critère 4 : le tarif du produit de réservation gratuite passe à 5 €.
    / Criterion 4: the free booking product's price becomes 5 €."""
    with tenant_context(lieu.client):
        Price.objects.filter(product__categorie_article=Product.FREERES).update(
            prix=Decimal("5.00")
        )
    connection.set_schema_to_public()


def poser_un_tag(lieu, registre):
    """Critère 5 : une ligne dans `BaseBillet_tag`, table que ni l'onboarding ni les
    migrations ne remplissent. / Criterion 5: a row in a table nobody fills on creation."""
    with tenant_context(lieu.client):
        Tag.objects.bulk_create([Tag(name="Tag du test", slug="tag-du-test")])
    connection.set_schema_to_public()


def poser_un_logo(lieu, registre):
    """Critère 6 : un logo dans la configuration. / Criterion 6: a logo."""
    with tenant_context(lieu.client):
        Configuration.objects.filter(pk=Configuration.singleton_instance_id).update(
            logo="images/logo_du_test_nettoyage.png"
        )
    connection.set_schema_to_public()


def poser_laboutik_v1(lieu, registre):
    """Critère 6 : un serveur LaBoutik V1. / Criterion 6: a LaBoutik V1 server."""
    with tenant_context(lieu.client):
        Configuration.objects.filter(pk=Configuration.singleton_instance_id).update(
            server_cashless="https://laboutik.nettoyage.test"
        )
    connection.set_schema_to_public()


def poser_une_monnaie_federee(lieu, registre):
    """Critère 7 : le lieu est fédéré à une monnaie Fedow créée par un autre lieu (la ligne
    `Client` du schéma public, jamais un lieu de démo).
    / Criterion 7: the venue is federated to a Fedow currency of another venue."""
    autre_lieu = Client.objects.get(schema_name=get_public_schema_name())
    portefeuille_de_la_monnaie = Wallet.objects.create(
        name=f"Portefeuille nettoyage {uuid.uuid4().hex[:8]}"
    )
    registre.uuids_des_portefeuilles.append(portefeuille_de_la_monnaie.pk)
    monnaie = AssetFedowPublic.objects.create(
        name=f"Monnaie nettoyage {uuid.uuid4().hex[:8]}",
        currency_code="TNE",
        wallet_origin=portefeuille_de_la_monnaie,
        origin=autre_lieu,
        category=AssetFedowPublic.TOKEN_LOCAL_FIAT,
    )
    registre.uuids_des_monnaies.append(monnaie.pk)
    monnaie.federated_with.add(lieu.client)


def poser_une_carte_nfc(lieu, registre):
    """Critère 7 : des cartes NFC ont le lieu pour origine.
    / Criterion 7: NFC cards with the venue as origin."""
    carte = Detail.objects.create(
        origine=lieu.client,
        generation=1,
        base_url=f"TEST-NETTOYAGE-{uuid.uuid4().hex[:8]}",
    )
    registre.pks_des_cartes.append(carte.pk)


def poser_un_droit_create_event(lieu, registre):
    """Critère 7 : un utilisateur a le droit de créer des événements dans le lieu.
    / Criterion 7: a user may create events in the venue."""
    utilisateur = creer_un_utilisateur(registre)
    utilisateur.create_event.add(lieu.client)


def faire_citer_le_lieu_par_un_autre_lieu(lieu, registre):
    """Critère 8 : un autre lieu jetable cite le lieu dans ses `FederatedPlace`.
    / Criterion 8: another disposable venue cites the venue."""
    lieu_voisin = creer_un_lieu_jetable(registre, "voisin")
    with tenant_context(lieu_voisin.client):
        FederatedPlace.objects.bulk_create([FederatedPlace(tenant=lieu.client)])
    connection.set_schema_to_public()


CAS_QUI_GARDENT_LE_LIEU = [
    pytest.param(passer_le_lieu_en_categorie_pool, 1, id="critere1-categorie-pool"),
    pytest.param(rajeunir_le_lieu, 2, id="critere2-cree-il-y-a-10-jours"),
    pytest.param(poser_un_evenement, 3, id="critere3-evenement"),
    pytest.param(poser_une_ligne_de_vente, 3, id="critere3-ligne-de-vente"),
    pytest.param(poser_une_adhesion, 3, id="critere3-adhesion"),
    pytest.param(poser_un_paiement_stripe, 3, id="critere3-paiement-stripe"),
    pytest.param(poser_un_produit_d_adhesion, 4, id="critere4-produit-d-adhesion"),
    pytest.param(poser_un_prix_non_nul, 4, id="critere4-prix-non-nul"),
    pytest.param(poser_un_tag, 5, id="critere5-tag"),
    pytest.param(poser_un_logo, 6, id="critere6-logo"),
    pytest.param(poser_laboutik_v1, 6, id="critere6-laboutik-v1"),
    pytest.param(poser_une_monnaie_federee, 7, id="critere7-monnaie-federee"),
    pytest.param(poser_une_carte_nfc, 7, id="critere7-carte-nfc"),
    pytest.param(poser_un_droit_create_event, 7, id="critere7-droit-create-event"),
    pytest.param(
        faire_citer_le_lieu_par_un_autre_lieu, 8, id="critere8-cite-par-un-lieu"
    ),
]


# ==========================================================================
# 1 — À blanc
# ==========================================================================


def test_a_blanc_n_ecrit_rien(registre, tmp_path):
    """
    Un lieu neuf, inactif, ancien. À blanc (sans `--executer`, sans `--liste`) : il est
    listé « à supprimer » avec la raison « aucune activité », et rien n'est écrit : son
    schéma, sa ligne `Client` et son domaine sont toujours là.
    C'est l'un des trois tests SANS `--liste` : il prouve le passage à blanc complet, celui
    que le mainteneur lit pour écrire sa liste.
    / Dry run: listed "to delete" with "no activity"; schema, Client, domain still there.
    One of the three tests WITHOUT --liste: it proves the full dry run.
    """
    lieu = creer_un_lieu_jetable(registre, "blanc")
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    lancer_la_commande("--rapport", chemin_du_rapport)

    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    ligne = ligne_du_lieu(lignes, lieu)

    assert ligne is not None, "Le lieu inactif n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_A_SUPPRIMER
    assert RAISON_D_UN_LIEU_SUPPRIME in ligne[COLONNE_RAISONS].lower()
    assert schema_exists(lieu.nom_du_schema)
    assert le_client_existe(lieu)
    assert le_domaine_existe(lieu)


# ==========================================================================
# 2 — Exécution
# ==========================================================================


def test_lieu_inactif_supprime_avec_execution(registre, tmp_path):
    """
    Deux lieux inactifs ; seul le premier est dans la liste. Avec `--executer` : le
    premier n'a plus de schéma, ni de ligne `Client`, ni de domaine ; il est « supprimé »
    dans le rapport. Le second, hors de la liste, est intact.
    / Two inactive venues, only the first listed: the first is fully deleted, the
    second (not listed) is untouched.
    """
    lieu_de_la_liste = creer_un_lieu_jetable(registre, "liste")
    lieu_hors_liste = creer_un_lieu_jetable(registre, "horsliste")
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu_de_la_liste])
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    lancer_la_commande(
        "--executer", "--liste", chemin_de_la_liste, "--rapport", chemin_du_rapport
    )

    assert not schema_exists(lieu_de_la_liste.nom_du_schema)
    assert not le_client_existe(lieu_de_la_liste)
    assert not le_domaine_existe(lieu_de_la_liste)
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    assert ligne_du_lieu(lignes, lieu_de_la_liste)[COLONNE_LISTE] == LISTE_SUPPRIME

    assert schema_exists(lieu_hors_liste.nom_du_schema)
    assert le_client_existe(lieu_hors_liste)
    assert le_domaine_existe(lieu_hors_liste)


# ==========================================================================
# 3 — Utilisateurs et portefeuilles gardés
# ==========================================================================


def test_utilisateurs_et_portefeuilles_gardes(registre, tmp_path):
    """
    L'administrateur du lieu a le lieu pour `client_source`, `client_admin` et
    `client_achat`, et un portefeuille dont l'origine est le lieu. Après la suppression :
    l'utilisateur existe toujours, son `client_source` est vide, il n'est plus relié au
    lieu ; son portefeuille existe toujours, toujours à lui, avec une origine vide.
    / After deletion: user kept, client_source empty, M2M links gone; wallet kept, still
    his, origin empty.
    """
    lieu = creer_un_lieu_jetable(registre, "utilisateurs")
    administrateur = creer_un_administrateur_des_lieux(registre, [lieu])
    administrateur.client_achat.add(lieu.client)
    portefeuille = Wallet.objects.create(
        name=f"Portefeuille nettoyage {uuid.uuid4().hex[:8]}", origin=lieu.client
    )
    registre.uuids_des_portefeuilles.append(portefeuille.pk)
    TibilletUser.objects.filter(pk=administrateur.pk).update(
        client_source=lieu.client, wallet=portefeuille
    )
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])

    lancer_la_commande("--executer", "--liste", chemin_de_la_liste)

    assert not schema_exists(lieu.nom_du_schema), "Le lieu n'a pas été supprimé."
    administrateur_relu = TibilletUser.objects.get(pk=administrateur.pk)
    assert administrateur_relu.client_source_id is None
    assert administrateur_relu.client_admin.count() == 0
    assert administrateur_relu.client_achat.count() == 0
    portefeuille_relu = Wallet.objects.get(pk=portefeuille.pk)
    assert portefeuille_relu.origin_id is None
    assert administrateur_relu.wallet_id == portefeuille.pk


# ==========================================================================
# 4 — Chaque critère garde le lieu
# ==========================================================================


@pytest.mark.parametrize(
    "rendre_le_lieu_actif, numero_du_critere", CAS_QUI_GARDENT_LE_LIEU
)
def test_chaque_critere_garde_le_lieu(
    registre, tmp_path, rendre_le_lieu_actif, numero_du_critere
):
    """
    Un lieu neuf, puis UNE chose qui le rend actif. À blanc : il n'est pas « à supprimer » ;
    il est « gardé », et ses raisons nomment le bon critère du §18.
    Critère 1 : le lieu du pool a un domaine principal, il apparaît donc, « gardé » (un
    emplacement du pool SANS domaine n'apparaît pas : test 14).
    / One thing makes the venue active: kept, with the right criterion named.
    """
    lieu = creer_un_lieu_jetable(registre, "critere")
    rendre_le_lieu_actif(lieu, registre)

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    libelle_attendu = LIBELLE_DU_CRITERE[numero_du_critere]
    assert ligne is not None, "Le lieu actif n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_GARDE
    assert libelle_attendu in ligne[COLONNE_RAISONS].lower(), (
        f"Raison attendue « {libelle_attendu} », lue : « {ligne[COLONNE_RAISONS]} »"
    )


# ==========================================================================
# 5 — Une table inconnue non vide garde le lieu
# ==========================================================================


def test_table_inconnue_non_vide_garde_le_lieu(registre, tmp_path):
    """
    Une table créée par le test dans le schéma du lieu, avec une ligne : aucune liste de
    l'outil ne peut la connaître. Le lieu est gardé (critère 5 : « une table inconnue non
    vide → lieu gardé »).
    / An unknown non-empty table in the venue schema keeps the venue.
    """
    lieu = creer_un_lieu_jetable(registre, "tableinconnue")
    with connection.cursor() as curseur:
        curseur.execute(
            f'CREATE TABLE "{lieu.nom_du_schema}".table_inconnue_du_test (id integer)'
        )
        curseur.execute(
            f'INSERT INTO "{lieu.nom_du_schema}".table_inconnue_du_test (id) VALUES (1)'
        )

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_GARDE
    assert LIBELLE_DU_CRITERE[5] in ligne[COLONNE_RAISONS].lower()


# ==========================================================================
# 5 ter — Le plan comptable de main : seulement ses 9 comptes par défaut
# ==========================================================================

# Les 9 comptes semés par `main:comptabilite/migrations/0002` (fiche 05-R §12 étape 3),
# écrits ici à la main, jamais importés de l'outil : un compte oublié dans l'outil doit
# se voir.
# / The 9 accounts seeded by main's comptabilite 0002, written by hand (never imported).
COMPTES_DU_PLAN_PAR_DEFAUT_DE_MAIN = [
    "411000",
    "4457100",
    "4457200",
    "4457300",
    "511000",
    "512000",
    "530000",
    "706000",
    "756000",
]


def recreer_le_plan_comptable_de_main(lieu, numeros_des_comptes):
    """
    Recrée dans le schéma du lieu la table `comptabilite_comptecomptable` de `main`, avec
    les comptes donnés. Sur la branche, la migration `comptabilite 0005` a supprimé cette
    table : un lieu neuf de la branche ne l'a pas. En production, la nuit de la bascule
    (base de `main`, avant les migrations), elle existe. La table part avec le schéma du
    lieu en fin de test.
    / Recreates main's comptabilite_comptecomptable table in the venue schema, with the
    given accounts. It goes away with the venue schema.
    """
    with connection.cursor() as curseur:
        curseur.execute(
            f'CREATE TABLE "{lieu.nom_du_schema}"."comptabilite_comptecomptable" ('
            f"  id bigserial PRIMARY KEY,"
            f"  numero varchar(12) NOT NULL UNIQUE,"
            f"  libelle varchar(120) NOT NULL DEFAULT '',"
            f"  type_compte varchar(1) NOT NULL DEFAULT 'X',"
            f"  actif boolean NOT NULL DEFAULT true"
            f")"
        )
        for numero_du_compte in numeros_des_comptes:
            curseur.execute(
                f'INSERT INTO "{lieu.nom_du_schema}"."comptabilite_comptecomptable" '
                f"(numero) VALUES (%s)",
                [numero_du_compte],
            )


@pytest.mark.parametrize(
    "comptes_en_plus, liste_attendue",
    [
        pytest.param([], LISTE_A_SUPPRIMER, id="les-9-comptes-par-defaut"),
        pytest.param(["706100"], LISTE_GARDE, id="un-10e-compte"),
    ],
)
def test_plan_comptable_de_main_seulement_ses_comptes_par_defaut(
    registre, tmp_path, comptes_en_plus, liste_attendue
):
    """
    Un lieu neuf avec la table `comptabilite_comptecomptable` de `main` :
    - exactement les 9 comptes du plan par défaut : le lieu reste « à supprimer » ;
    - un 10ᵉ compte : le lieu est « gardé », et la raison nomme la table.
    / Main's chart of accounts: the 9 default accounts are tolerated, a 10th keeps the venue.
    """
    lieu = creer_un_lieu_jetable(registre, "plancomptable")
    recreer_le_plan_comptable_de_main(
        lieu, COMPTES_DU_PLAN_PAR_DEFAUT_DE_MAIN + comptes_en_plus
    )

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert "comptabilite_comptecomptable" in ligne[COLONNE_RAISONS]


# ==========================================================================
# 5 sexies — Un groupe de ressources garde le lieu
# ==========================================================================


def test_un_groupe_de_ressources_garde_le_lieu(registre, tmp_path):
    """
    Aucune migration ne sème de groupe de ressources : un lieu neuf n'en a pas.
    Un groupe est donc l'œuvre du lieu : il est « gardé »
    (« table non vide : booking_resourcegroup »).
    Le groupe s'appelle « Ressource », un nom qu'un semis par défaut pourrait porter :
    le lieu doit être gardé quand même. Aucun nom de groupe n'est toléré.
    / No migration seeds resource groups: a group keeps the venue, whatever its name.
    """
    lieu = creer_un_lieu_jetable(registre, "groupes")
    with tenant_context(lieu.client):
        assert ResourceGroup.objects.count() == 0, "Condition : aucun groupe semé."
        ResourceGroup.objects.bulk_create([ResourceGroup(name="Ressource")])
    connection.set_schema_to_public()

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_GARDE, ligne[COLONNE_RAISONS]
    assert "booking_resourcegroup" in ligne[COLONNE_RAISONS]


# ==========================================================================
# 5 quater — Les clôtures de main : seulement à montant nul
# ==========================================================================


def recreer_les_clotures_de_main(lieu, total_general, nombre_transactions):
    """
    Remplace dans le schéma du lieu la table `comptabilite_cloturecaisse` par celle de
    `main` (colonnes de `main:comptabilite/models.py`, `ClotureCaisse`), avec UNE clôture
    journalière. La nuit de la bascule, la base est celle de `main` : c'est cette table que
    l'outil lit. Elle part avec le schéma du lieu en fin de test.
    Les valeurs par défaut sont posées dans la table (Django ne les met pas en base) pour
    n'écrire que les colonnes qui comptent.
    / Replaces the venue's comptabilite_cloturecaisse with main's table and ONE daily
    closure. It goes away with the venue schema.
    """
    nom_complet_de_la_table = f'"{lieu.nom_du_schema}"."comptabilite_cloturecaisse"'
    with connection.cursor() as curseur:
        curseur.execute(f"DROP TABLE IF EXISTS {nom_complet_de_la_table} CASCADE")
        curseur.execute(
            f"CREATE TABLE {nom_complet_de_la_table} ("
            f"  uuid uuid PRIMARY KEY,"
            f"  niveau varchar(1) NOT NULL DEFAULT 'J',"
            f"  numero_sequentiel integer NOT NULL UNIQUE,"
            f"  datetime_debut timestamp with time zone NOT NULL DEFAULT now(),"
            f"  datetime_fin timestamp with time zone NOT NULL DEFAULT now(),"
            f"  responsable_id uuid NULL,"
            f"  total_general integer NOT NULL DEFAULT 0,"
            f"  total_ht integer NOT NULL DEFAULT 0,"
            f"  total_tva integer NOT NULL DEFAULT 0,"
            f"  nombre_transactions integer NOT NULL DEFAULT 0,"
            f"  total_perpetuel integer NOT NULL DEFAULT 0,"
            f"  hash_lignes varchar(64) NOT NULL DEFAULT '',"
            f"  rapport_json jsonb NOT NULL DEFAULT '{{}}',"
            f"  created_at timestamp with time zone NOT NULL DEFAULT now()"
            f")"
        )
        curseur.execute(
            f"INSERT INTO {nom_complet_de_la_table} "
            f"(uuid, numero_sequentiel, total_general, nombre_transactions) "
            f"VALUES (%s, 1, %s, %s)",
            [str(uuid.uuid4()), total_general, nombre_transactions],
        )


@pytest.mark.parametrize(
    "total_general, nombre_transactions, liste_attendue",
    [
        pytest.param(0, 0, LISTE_A_SUPPRIMER, id="cloture-a-zero"),
        pytest.param(1, 0, LISTE_GARDE, id="cloture-a-un-centime"),
        pytest.param(0, 1, LISTE_GARDE, id="cloture-a-zero-avec-une-transaction"),
    ],
)
def test_clotures_de_main_seulement_a_montant_nul(
    registre, tmp_path, total_general, nombre_transactions, liste_attendue
):
    """
    Un lieu neuf avec une clôture journalière de `main` :
    - à 0 € et sans transaction (clôture automatique d'un lieu vide) : « à supprimer » ;
    - à 1 centime, ou à 0 € avec une transaction : « gardé », la raison nomme la table.
    / Main's closures: a zero closure is tolerated, any amount or transaction keeps it.
    """
    lieu = creer_un_lieu_jetable(registre, "clotures")
    recreer_les_clotures_de_main(lieu, total_general, nombre_transactions)

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert "comptabilite_cloturecaisse" in ligne[COLONNE_RAISONS]


# ==========================================================================
# 5 quinquies — Les taux de TVA : seulement ceux semés par main (BaseBillet 0187)
# ==========================================================================


@pytest.mark.parametrize(
    "taux_ajoute, liste_attendue",
    [
        pytest.param(None, LISTE_A_SUPPRIMER, id="taux-par-defaut"),
        pytest.param(Decimal("7.00"), LISTE_GARDE, id="un-taux-ajoute"),
    ],
)
def test_taux_de_tva_seulement_ceux_semes_par_main(
    registre, tmp_path, taux_ajoute, liste_attendue
):
    """
    Un lieu neuf a les 6 taux semés par `main:BaseBillet/migrations/0187` (0 ; 2,10 ; 5,50 ;
    8,50 ; 10 ; 20) : il reste « à supprimer ». Un autre taux, ajouté par le lieu, le garde :
    « table non vide : BaseBillet_tva (taux ajoutés) ».
    / The 6 rates seeded by main's 0187 are tolerated; another rate keeps the venue.
    """
    lieu = creer_un_lieu_jetable(registre, "tva")
    if taux_ajoute is not None:
        with tenant_context(lieu.client):
            Tva.objects.bulk_create([Tva(tva_rate=taux_ajoute)])
        connection.set_schema_to_public()

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert "BaseBillet_tva" in ligne[COLONNE_RAISONS]


# ==========================================================================
# 6 ter — L'habillage (`skin`) de main : seulement « reunion »
# ==========================================================================


@pytest.mark.parametrize(
    "habillage, liste_attendue",
    [
        pytest.param("reunion", LISTE_A_SUPPRIMER, id="habillage-par-defaut"),
        pytest.param("faire_festival", LISTE_GARDE, id="habillage-choisi"),
    ],
)
def test_habillage_de_main_seulement_le_defaut(
    registre, tmp_path, habillage, liste_attendue
):
    """
    La colonne `skin` de la configuration existe sur `main` (défaut « reunion ») ; la
    migration `0226` de la branche la retire. Elle est recréée ici dans le lieu jetable.
    Valeur « reunion » : le lieu reste « à supprimer ». Une autre valeur : le lieu a choisi
    son habillage, il est « gardé » (« configuration personnalisée : … skin … »).
    / Main's `skin` column, recreated: "reunion" is the default, another value keeps it.
    """
    lieu = creer_un_lieu_jetable(registre, "habillage")
    with connection.cursor() as curseur:
        curseur.execute(
            f'ALTER TABLE "{lieu.nom_du_schema}"."BaseBillet_configuration" '
            f"ADD COLUMN skin varchar(20) NOT NULL DEFAULT 'reunion'"
        )
        curseur.execute(
            f'UPDATE "{lieu.nom_du_schema}"."BaseBillet_configuration" SET skin = %s',
            [habillage],
        )

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert LIBELLE_DU_CRITERE[6] in ligne[COLONNE_RAISONS].lower()
        assert "skin" in ligne[COLONNE_RAISONS]


# ==========================================================================
# 2 bis — La limite des jours : « plus de 60 jours »
# ==========================================================================


@pytest.mark.parametrize(
    "age_en_jours, liste_attendue",
    [
        pytest.param(60, LISTE_GARDE, id="exactement-60-jours"),
        pytest.param(61, LISTE_A_SUPPRIMER, id="61-jours"),
    ],
)
def test_limite_des_jours_minimum(registre, tmp_path, age_en_jours, liste_attendue):
    """
    Critère 2 : un lieu doit avoir été créé il y a PLUS de `--jours-minimum` jours (60 par
    défaut). Créé il y a exactement 60 jours : « gardé ». Il y a 61 jours : « à supprimer ».
    / Criterion 2: exactly 60 days old is kept, 61 days old is to delete.
    """
    lieu = creer_un_lieu_jetable(registre, "limite", age_en_jours=age_en_jours)

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert LIBELLE_DU_CRITERE[2] in ligne[COLONNE_RAISONS].lower()


# ==========================================================================
# 6 bis — Une newsletter branchée garde le lieu (critère 6)
# ==========================================================================


@pytest.mark.parametrize(
    "modele_des_reglages, valeurs_des_reglages, liste_attendue, nom_attendu",
    [
        pytest.param(
            GhostConfig,
            {"ghost_key": "cle-ghost-du-test"},
            LISTE_GARDE,
            "Ghost",
            id="ghost-cle",
        ),
        pytest.param(
            GhostConfig,
            {"ghost_url": "https://ghost.nettoyage.test"},
            LISTE_GARDE,
            "Ghost",
            id="ghost-adresse",
        ),
        pytest.param(
            GhostConfig,
            {"ghost_url": "", "ghost_key": None},
            LISTE_A_SUPPRIMER,
            None,
            id="ghost-vide",
        ),
        pytest.param(
            BrevoConfig,
            {"api_key": "cle-brevo-du-test"},
            LISTE_GARDE,
            "Brevo",
            id="brevo-cle",
        ),
        pytest.param(
            FormbricksConfig,
            {"api_key": "cle-formbricks-du-test"},
            LISTE_GARDE,
            "Formbricks",
            id="formbricks-cle",
        ),
        pytest.param(
            FormbricksConfig,
            {"api_key": None, "api_host": "https://app.formbricks.com"},
            LISTE_A_SUPPRIMER,
            None,
            id="formbricks-adresse-seule",
        ),
    ],
)
def test_newsletter_branchee_garde_le_lieu(
    registre,
    tmp_path,
    modele_des_reglages,
    valeurs_des_reglages,
    liste_attendue,
    nom_attendu,
):
    """
    Un lieu neuf avec la ligne de réglages d'un service de newsletter ou de formulaires :
    - une clé ou une adresse Ghost, une clé Brevo, une clé Formbricks : le lieu a branché
      le service, il est « gardé » avec « configuration personnalisée : <service> » ;
    - des réglages vides (NULL ou texte vide), ou seulement l'adresse de Formbricks
      (remplie dans des centaines de lieux sans clé) : le lieu reste « à supprimer ».
    Les réglages sont écrits par `bulk_create()` (aucun `save()`, rien dans memcached) ;
    la clé est un texte quelconque : l'outil ne lit que si la colonne est vide.
    / Newsletter settings: a key (or Ghost URL) keeps the venue; empty settings or the
    Formbricks host alone do not.
    """
    lieu = creer_un_lieu_jetable(registre, "newsletter")
    with tenant_context(lieu.client):
        modele_des_reglages.objects.bulk_create(
            [
                modele_des_reglages(
                    pk=modele_des_reglages.singleton_instance_id,
                    **valeurs_des_reglages,
                )
            ]
        )
    connection.set_schema_to_public()

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == liste_attendue, ligne[COLONNE_RAISONS]
    if liste_attendue == LISTE_GARDE:
        assert LIBELLE_DU_CRITERE[6] in ligne[COLONNE_RAISONS].lower()
        assert nom_attendu in ligne[COLONNE_RAISONS]


# ==========================================================================
# 5 bis — La page d'accueil par défaut (BaseBillet 0225) est tolérée
# ==========================================================================


def creer_la_page_d_accueil_par_defaut(lieu):
    """
    Crée dans le lieu la page d'accueil que la migration `BaseBillet 0225` crée dans un lieu
    qui a une configuration : même service (`pages.services.construire_page_accueil`),
    billetterie et adhésions allumées (les défauts) : 1 page d'accueil et 3 blocs (bannière,
    texte, appel à l'action). La configuration passée au service est un objet EN MÉMOIRE,
    jamais enregistré (tests/PIEGES.md 13.22).
    / Creates the home page that BaseBillet 0225 creates: same service, 1 page and 3 blocks.
    In-memory configuration, never saved.
    """
    configuration_en_memoire = Configuration(
        organisation=lieu.nom,
        module_billetterie=True,
        module_adhesion=True,
    )
    with tenant_context(lieu.client):
        page_d_accueil = construire_page_accueil(Page, Bloc, configuration_en_memoire)
        assert Page.objects.count() == 1
        assert Bloc.objects.filter(page=page_d_accueil).count() == 3
    connection.set_schema_to_public()
    return page_d_accueil


def test_page_d_accueil_par_defaut_toleree(registre, tmp_path):
    """
    Un lieu neuf avec exactement la page d'accueil de `BaseBillet 0225` et ses 3 blocs :
    il est « à supprimer ». Sans cette tolérance, un passage à blanc sur une base migrée
    garderait tous les lieux.
    / A venue with exactly the default home page and its 3 blocks is "to delete".
    """
    lieu = creer_un_lieu_jetable(registre, "accueil")
    creer_la_page_d_accueil_par_defaut(lieu)

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_A_SUPPRIMER, ligne[COLONNE_RAISONS]


@pytest.mark.parametrize(
    "ajout_au_dela_du_defaut, table_attendue",
    [
        ("quatrieme_bloc", "pages_bloc"),
        ("deuxieme_page", "pages_page"),
    ],
)
def test_page_d_accueil_au_dela_du_defaut_garde_le_lieu(
    registre, tmp_path, ajout_au_dela_du_defaut, table_attendue
):
    """
    La page d'accueil par défaut, plus UNE ligne que la migration ne crée pas : un 4ᵉ bloc
    sur la page d'accueil, ou une 2ᵉ page (qui n'est pas l'accueil). Le lieu est gardé,
    avec « table non vide : <la table> ».
    / Default home page plus a 4th block or a 2nd page: kept, "table non vide".
    """
    lieu = creer_un_lieu_jetable(registre, "accueilplus")
    page_d_accueil = creer_la_page_d_accueil_par_defaut(lieu)
    with tenant_context(lieu.client):
        if ajout_au_dela_du_defaut == "quatrieme_bloc":
            Bloc.objects.create(
                page=page_d_accueil,
                type_bloc="TEXTE",
                position=4,
                texte="Un bloc ajouté par le lieu.",
            )
        if ajout_au_dela_du_defaut == "deuxieme_page":
            Page.objects.create(
                titre="Une page ajoutée par le lieu",
                slug=f"page-du-test-{uuid.uuid4().hex[:8]}",
                est_accueil=False,
            )
    connection.set_schema_to_public()

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_GARDE
    raisons_en_minuscules = ligne[COLONNE_RAISONS].lower()
    assert LIBELLE_DU_CRITERE[5] in raisons_en_minuscules
    assert table_attendue.lower() in raisons_en_minuscules


# ==========================================================================
# 6 — `--executer` sans `--liste`
# ==========================================================================


def test_execution_sans_liste_refusee(registre, tmp_path):
    """
    `--executer` sans `--liste` : la commande s'arrête en erreur (`CommandError` qui
    nomme l'option manquante), et rien n'est écrit : le lieu inactif est intact.
    / --executer without --liste: CommandError, nothing written.
    """
    lieu = creer_un_lieu_jetable(registre, "sansliste")

    with pytest.raises(CommandError) as erreur:
        lancer_la_commande("--executer")

    assert "liste" in str(erreur.value)
    assert schema_exists(lieu.nom_du_schema)
    assert le_client_existe(lieu)
    assert le_domaine_existe(lieu)


# ==========================================================================
# 7 — Lieu de la liste redevenu actif
# ==========================================================================


def test_lieu_de_la_liste_redevenu_actif_garde(registre, tmp_path):
    """
    Le lieu est dans la liste validée, mais il a maintenant un événement. Avec
    `--executer` : il est gardé (schéma et `Client` là, « gardé » dans le rapport) et
    signalé sur la sortie, sur la ligne de son domaine.
    / Listed but now active: kept and reported on the output.
    """
    lieu = creer_un_lieu_jetable(registre, "redevenuactif")
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])
    poser_un_evenement(lieu, registre)
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    resultat = lancer_la_commande(
        "--executer", "--liste", chemin_de_la_liste, "--rapport", chemin_du_rapport
    )

    assert schema_exists(lieu.nom_du_schema)
    assert le_client_existe(lieu)
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    assert ligne_du_lieu(lignes, lieu)[COLONNE_LISTE] == LISTE_GARDE

    lignes_qui_signalent_le_lieu = []
    for ligne_de_sortie in resultat.sortie.splitlines():
        if lieu.domaine in ligne_de_sortie and (
            PHRASE_LIEU_DE_LA_LISTE_REDEVENU_ACTIF in ligne_de_sortie
        ):
            lignes_qui_signalent_le_lieu.append(ligne_de_sortie)
    assert lignes_qui_signalent_le_lieu, resultat.sortie


# ==========================================================================
# 8 — Une référence apparue après le passage à blanc garde le lieu
# ==========================================================================


def test_reference_apparue_apres_le_passage_a_blanc_garde_le_lieu(registre, tmp_path):
    """
    Le premier lieu est « à supprimer » au passage à blanc. ENSUITE, avant `--executer`,
    une table publique inconnue de la commande se met à pointer vers lui (comme une ligne
    écrite entre la validation de la liste et la nuit). Avec `--executer`, la détection
    refaite voit la référence : le lieu est « gardé », son schéma, sa ligne `Client` et son
    domaine sont toujours là. Un lieu retenu n'arrête pas les autres : le second lieu de la
    liste est supprimé.
    L'annulation d'une transaction déjà commencée est prouvée par le test 8 ter.
    / A reference appearing after the dry run keeps the venue (seen at detection). The
    rollback of a started transaction is proved by test 8 ter.
    """
    lieu_retenu = creer_un_lieu_jetable(registre, "retenu")
    lieu_libre = creer_un_lieu_jetable(registre, "libre")

    ligne_a_blanc = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu_retenu)
    assert ligne_a_blanc is not None
    assert ligne_a_blanc[COLONNE_LISTE] == LISTE_A_SUPPRIMER

    creer_une_table_qui_pointe_vers_le_lieu(
        registre, lieu_retenu, get_public_schema_name()
    )

    chemin_de_la_liste = ecrire_la_liste_des_domaines(
        tmp_path, [lieu_retenu, lieu_libre]
    )
    chemin_du_rapport = str(tmp_path / "rapport.csv")
    lancer_la_commande(
        "--executer", "--liste", chemin_de_la_liste, "--rapport", chemin_du_rapport
    )

    assert schema_exists(lieu_retenu.nom_du_schema)
    assert le_client_existe(lieu_retenu)
    assert le_domaine_existe(lieu_retenu)
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    ligne_du_lieu_retenu = ligne_du_lieu(lignes, lieu_retenu)
    assert ligne_du_lieu_retenu is not None
    assert ligne_du_lieu_retenu[COLONNE_LISTE] == LISTE_GARDE

    assert not schema_exists(lieu_libre.nom_du_schema)
    assert not le_client_existe(lieu_libre)


# ==========================================================================
# 8 bis — Une référence inconnue garde le lieu dès la détection
# ==========================================================================


@pytest.mark.parametrize("ou_est_la_table", ["schema_public", "schema_d_un_autre_lieu"])
def test_reference_inconnue_garde_le_lieu_des_la_detection(
    registre, tmp_path, ou_est_la_table
):
    """
    Une table inconnue de la commande, dans le schéma public ou dans le schéma d'un autre
    lieu, a une ligne qui pointe vers le lieu. Au passage à blanc, le lieu est « gardé »
    avec la raison « référence inconnue » : le mainteneur la voit avant la nuit.
    / An unknown table (public or another venue) pointing to the venue keeps it at
    detection, reason "unknown reference".
    """
    lieu = creer_un_lieu_jetable(registre, "reference")
    if ou_est_la_table == "schema_public":
        nom_du_schema_de_la_table = get_public_schema_name()
    if ou_est_la_table == "schema_d_un_autre_lieu":
        lieu_voisin = creer_un_lieu_jetable(registre, "voisin")
        nom_du_schema_de_la_table = lieu_voisin.nom_du_schema
    creer_une_table_qui_pointe_vers_le_lieu(registre, lieu, nom_du_schema_de_la_table)

    ligne = lancer_a_blanc_et_lire_la_ligne(tmp_path, lieu)

    assert ligne is not None, "Le lieu n'est pas dans le rapport."
    assert ligne[COLONNE_LISTE] == LISTE_GARDE
    assert RAISON_REFERENCE_INCONNUE in ligne[COLONNE_RAISONS].lower()


# ==========================================================================
# 8 ter — Le contrôle par le catalogue annule la transaction du lieu
# ==========================================================================


def test_controle_du_catalogue_annule_la_suppression_du_lieu(registre, tmp_path):
    """
    Deux lieux inactifs de la liste ; le premier a un administrateur. Le contrôle par le
    catalogue (fait juste avant le COMMIT) est remplacé par un faux : pour le premier lieu
    seulement, il trouve une référence restante. Avec `--executer` :
    - la transaction du premier lieu est annulée : son schéma, sa ligne `Client` et son
      domaine sont toujours là ; il est en « échec » dans le rapport ;
    - aucune tâche de mail n'est demandée (rien pour un lieu en échec) ;
    - le second lieu est supprimé : un échec n'arrête pas les autres.
    C'est le seul test qui atteint une transaction qui échoue après le `DROP SCHEMA` : il
    tombe si le contrôle est retiré, ou si la suppression se fait hors transaction.
    / The catalogue check is faked to find a leftover reference for the first venue: its
    transaction is rolled back (schema, Client, domain intact, "échec"), no mail task,
    and the second venue is still deleted.
    """
    # Import ici : seul ce test dépend d'une fonction interne de la commande.
    # / Imported here: only this test depends on an internal function.
    from Administration import nettoyage_des_lieux

    lieu_retenu = creer_un_lieu_jetable(registre, "controle")
    lieu_libre = creer_un_lieu_jetable(registre, "libre")
    creer_un_administrateur_des_lieux(registre, [lieu_retenu])
    chemin_de_la_liste = ecrire_la_liste_des_domaines(
        tmp_path, [lieu_retenu, lieu_libre]
    )
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    vrai_controle_du_catalogue = nettoyage_des_lieux.references_restantes_vers_le_lieu

    def faux_controle_du_catalogue(curseur, uuid_du_lieu, domaine_par_schema):
        if uuid_du_lieu == str(lieu_retenu.client.pk):
            return ["table_restante_du_test"]
        return vrai_controle_du_catalogue(curseur, uuid_du_lieu, domaine_par_schema)

    with patch.object(
        nettoyage_des_lieux,
        "references_restantes_vers_le_lieu",
        side_effect=faux_controle_du_catalogue,
    ):
        resultat = lancer_la_commande(
            "--executer",
            "--liste",
            chemin_de_la_liste,
            "--rapport",
            chemin_du_rapport,
            schemas_a_surveiller=[lieu_retenu.nom_du_schema],
        )

    assert schema_exists(lieu_retenu.nom_du_schema)
    assert le_client_existe(lieu_retenu)
    assert le_domaine_existe(lieu_retenu)
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    assert ligne_du_lieu(lignes, lieu_retenu)[COLONNE_LISTE] == LISTE_ECHEC
    assert resultat.taches_demandees == []

    assert not schema_exists(lieu_libre.nom_du_schema)
    assert not le_client_existe(lieu_libre)
    assert ligne_du_lieu(lignes, lieu_libre)[COLONNE_LISTE] == LISTE_SUPPRIME


# ==========================================================================
# 9 — Le rapport désigne les lieux par leur domaine
# ==========================================================================


def test_rapport_designe_les_lieux_par_leur_domaine(registre, tmp_path):
    """
    Le rapport CSV a les colonnes domaine, date de création et raisons. La ligne du lieu
    porte son domaine principal et sa date de création. Le nom de son schéma n'apparaît
    nulle part : ni dans le CSV, ni sur la sortie.
    / The CSV has domain, creation date and reasons columns; the schema name appears
    nowhere.
    """
    lieu = creer_un_lieu_jetable(registre, "rapport")
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    resultat = lancer_la_commande(
        "--liste", chemin_de_la_liste, "--rapport", chemin_du_rapport
    )

    colonnes, lignes = lire_un_csv(chemin_du_rapport)
    assert COLONNE_DOMAINE in colonnes
    assert COLONNE_DATE_DE_CREATION in colonnes
    assert COLONNE_RAISONS in colonnes
    ligne = ligne_du_lieu(lignes, lieu)
    assert ligne is not None
    assert ligne[COLONNE_DATE_DE_CREATION] == lieu.date_de_creation.isoformat()

    with open(chemin_du_rapport, encoding="utf-8-sig") as fichier:
        texte_du_rapport = fichier.read()
    assert lieu.nom_du_schema not in texte_du_rapport
    assert lieu.nom_du_schema not in resultat.sortie


# ==========================================================================
# 10 — Les traces externes
# ==========================================================================


def test_traces_externes_ecrites(registre, tmp_path):
    """
    Le lieu a un compte Stripe Connect, un compte Stripe Connect de test (remplis par le
    formulaire de création) et une place Fedow. Après sa suppression, le CSV des traces
    externes a sa ligne : domaine, les deux identifiants Stripe Connect, place Fedow.
    / External traces CSV: domain, both Stripe Connect ids, Fedow place.
    """
    lieu = creer_un_lieu_jetable(registre, "traces")
    identifiant_stripe_connect = f"acct_{uuid.uuid4().hex[:16]}"
    identifiant_stripe_connect_test = f"acct_{uuid.uuid4().hex[:16]}"
    place_fedow = uuid.uuid4()
    with tenant_context(lieu.client):
        Configuration.objects.filter(pk=Configuration.singleton_instance_id).update(
            stripe_connect_account=identifiant_stripe_connect,
            stripe_connect_account_test=identifiant_stripe_connect_test,
        )
        FedowConfig.objects.bulk_create(
            [
                FedowConfig(
                    pk=FedowConfig.singleton_instance_id, fedow_place_uuid=place_fedow
                )
            ]
        )
    connection.set_schema_to_public()
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])
    chemin_des_traces = str(tmp_path / "traces_externes.csv")

    lancer_la_commande(
        "--executer",
        "--liste",
        chemin_de_la_liste,
        "--traces-externes",
        chemin_des_traces,
    )

    assert not schema_exists(lieu.nom_du_schema), "Le lieu n'a pas été supprimé."
    _colonnes, lignes = lire_un_csv(chemin_des_traces)
    ligne = ligne_du_lieu(lignes, lieu)
    assert ligne is not None
    assert ligne[COLONNE_STRIPE_CONNECT] == identifiant_stripe_connect
    assert ligne[COLONNE_STRIPE_CONNECT_TEST] == identifiant_stripe_connect_test
    assert ligne[COLONNE_PLACE_FEDOW] == str(place_fedow)


# ==========================================================================
# 10 bis — Les administrateurs dans les traces, et les lieux sans administrateur
# ==========================================================================


def test_traces_externes_avec_les_administrateurs_et_lieux_sans_administrateur(
    registre, tmp_path
):
    """
    Deux lieux inactifs supprimés : le premier a deux administrateurs, le second aucun.
    - Le CSV des traces externes a une colonne `administrateurs` : les adresses des
      administrateurs du lieu, lues avant la suppression, séparées par « ; ». Elle garde
      « qui prévenir » si la file des mails est perdue. Vide pour le lieu sans
      administrateur.
    - Le résumé compte « 1 lieux supprimés sans administrateur (aucun mail) ».
    / The external traces CSV lists the admins' addresses; the summary counts the deleted
    venues without admin.
    """
    lieu_avec_administrateurs = creer_un_lieu_jetable(registre, "avecadmin")
    lieu_sans_administrateur = creer_un_lieu_jetable(registre, "sansadmin")
    premier_administrateur = creer_un_administrateur_des_lieux(
        registre, [lieu_avec_administrateurs]
    )
    second_administrateur = creer_un_administrateur_des_lieux(
        registre, [lieu_avec_administrateurs]
    )
    chemin_de_la_liste = ecrire_la_liste_des_domaines(
        tmp_path, [lieu_avec_administrateurs, lieu_sans_administrateur]
    )
    chemin_des_traces = str(tmp_path / "traces_externes.csv")

    resultat = lancer_la_commande(
        "--executer",
        "--liste",
        chemin_de_la_liste,
        "--traces-externes",
        chemin_des_traces,
    )

    assert not schema_exists(lieu_avec_administrateurs.nom_du_schema)
    assert not schema_exists(lieu_sans_administrateur.nom_du_schema)
    colonnes, lignes = lire_un_csv(chemin_des_traces)
    assert COLONNE_ADMINISTRATEURS in colonnes

    adresses_lues = []
    texte_des_adresses = ligne_du_lieu(lignes, lieu_avec_administrateurs)[
        COLONNE_ADMINISTRATEURS
    ]
    for adresse in texte_des_adresses.split(";"):
        adresses_lues.append(adresse.strip())
    assert sorted(adresses_lues) == sorted(
        [premier_administrateur.email, second_administrateur.email]
    )
    assert (
        ligne_du_lieu(lignes, lieu_sans_administrateur)[COLONNE_ADMINISTRATEURS].strip()
        == ""
    )

    assert "1 lieux supprimés sans administrateur (aucun mail)" in resultat.sortie


# ==========================================================================
# 11 — Un mail par administrateur
# ==========================================================================


def test_un_mail_par_administrateur_apres_suppression(registre, tmp_path, mailoutbox):
    """
    Deux lieux inactifs ont le même administrateur. Avec `--executer` :
    - chaque tâche est demandée APRÈS le COMMIT : hors de toute transaction, quand les deux
      schémas n'existent plus ;
    - les tâches exécutées envoient UN mail, à cet administrateur, avec l'objet de la
      fiche et les deux domaines dedans.
    / Two venues, same admin: tasks queued after COMMIT; one mail with both domains.
    """
    premier_lieu = creer_un_lieu_jetable(registre, "mailun")
    second_lieu = creer_un_lieu_jetable(registre, "maildeux")
    administrateur = creer_un_administrateur_des_lieux(
        registre, [premier_lieu, second_lieu]
    )
    chemin_de_la_liste = ecrire_la_liste_des_domaines(
        tmp_path, [premier_lieu, second_lieu]
    )

    resultat = lancer_la_commande(
        "--executer",
        "--liste",
        chemin_de_la_liste,
        schemas_a_surveiller=[premier_lieu.nom_du_schema, second_lieu.nom_du_schema],
    )

    assert resultat.taches_demandees, "Aucune tâche de mail demandée."
    for tache_demandee in resultat.taches_demandees:
        assert tache_demandee.demandee_dans_une_transaction is False
        assert tache_demandee.schemas_encore_presents == []

    executer_les_taches_demandees(resultat.taches_demandees)

    assert len(mailoutbox) == 1
    mail_envoye = mailoutbox[0]
    assert mail_envoye.to == [administrateur.email]
    assert mail_envoye.subject == OBJET_DU_MAIL
    texte_du_mail = texte_complet_du_mail(mail_envoye)
    assert premier_lieu.domaine in texte_du_mail
    assert second_lieu.domaine in texte_du_mail
    assert "mutualisation" in texte_du_mail
    assert "https://tibillet.coop" in texte_du_mail


# ==========================================================================
# 12 — Aucun mail à blanc, avec --sans-mail, ni si la suppression est annulée
# ==========================================================================


@pytest.mark.parametrize("situation", ["a_blanc", "sans_mail", "suppression_annulee"])
def test_aucun_mail_a_blanc_ni_sans_mail_ni_si_annule(
    registre, tmp_path, mailoutbox, situation
):
    """
    Un lieu inactif avec un administrateur. Aucune tâche n'est demandée, aucun mail ne
    part :
    - à blanc ;
    - avec `--executer --sans-mail` (le lieu est bien supprimé) ;
    - avec `--executer` quand une référence inconnue retient le lieu (test 8 : gardé ou
      en échec, le lieu est toujours là).
    / No task, no mail: dry run, --sans-mail, or venue held by an unknown reference.
    """
    lieu = creer_un_lieu_jetable(registre, "sansmail")
    creer_un_administrateur_des_lieux(registre, [lieu])
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])

    if situation == "a_blanc":
        resultat = lancer_la_commande("--liste", chemin_de_la_liste)
        assert schema_exists(lieu.nom_du_schema)
    if situation == "sans_mail":
        resultat = lancer_la_commande(
            "--executer", "--liste", chemin_de_la_liste, "--sans-mail"
        )
        assert not schema_exists(lieu.nom_du_schema), "Le lieu n'a pas été supprimé."
    if situation == "suppression_annulee":
        creer_une_table_qui_pointe_vers_le_lieu(
            registre, lieu, get_public_schema_name()
        )
        resultat = lancer_la_commande("--executer", "--liste", chemin_de_la_liste)
        assert schema_exists(lieu.nom_du_schema)

    assert resultat.taches_demandees == []
    assert len(mailoutbox) == 0


# ==========================================================================
# 13 — Fiche d'onboarding supprimée
# ==========================================================================


def test_fiche_d_onboarding_supprimee(registre, tmp_path):
    """
    La fiche d'onboarding du lieu (`WaitingConfiguration`, elle porte les coordonnées du
    demandeur) n'existe plus après la suppression du lieu.
    / The venue's onboarding record is gone after deletion.
    """
    lieu = creer_un_lieu_jetable(registre, "fiche")
    fiche_d_onboarding = creer_une_fiche_d_onboarding(registre, lieu)
    chemin_de_la_liste = ecrire_la_liste_des_domaines(tmp_path, [lieu])

    lancer_la_commande("--executer", "--liste", chemin_de_la_liste)

    assert not schema_exists(lieu.nom_du_schema), "Le lieu n'a pas été supprimé."
    assert not WaitingConfiguration.objects.filter(pk=fiche_d_onboarding.pk).exists()


# ==========================================================================
# 14 — Un emplacement du pool sans domaine principal est ignoré
# ==========================================================================


def test_emplacement_du_pool_sans_domaine_ignore(registre, tmp_path):
    """
    Un emplacement du pool (catégorie `W`) sans domaine principal, ancien et inactif. Au
    passage à blanc complet, il n'apparaît dans aucune liste (aucune ligne du rapport ne
    le nomme, aucune ligne n'a un domaine vide), et le résumé chiffré dit « N emplacements
    du pool ignorés ».
    C'est l'un des trois tests SANS `--liste` : un lieu sans domaine ne peut pas être
    dans une liste de domaines.
    / A pool slot without a primary domain appears in no list; the summary counts the
    ignored pool slots. Full dry run, without --liste.
    """
    emplacement_du_pool = creer_un_lieu_jetable(
        registre, "pool", avec_domaine_principal=False
    )
    Client.objects.filter(pk=emplacement_du_pool.client.pk).update(
        categorie=Client.WAITING_CONFIG
    )
    chemin_du_rapport = str(tmp_path / "rapport.csv")

    resultat = lancer_la_commande("--rapport", chemin_du_rapport)

    with open(chemin_du_rapport, encoding="utf-8-sig") as fichier:
        texte_du_rapport = fichier.read()
    assert emplacement_du_pool.nom_du_schema not in texte_du_rapport
    assert emplacement_du_pool.nom not in texte_du_rapport
    _colonnes, lignes = lire_un_csv(chemin_du_rapport)
    for ligne in lignes:
        assert ligne[COLONNE_DOMAINE] != "", "Une ligne du rapport n'a pas de domaine."
    assert PHRASE_EMPLACEMENTS_DU_POOL_IGNORES in resultat.sortie
