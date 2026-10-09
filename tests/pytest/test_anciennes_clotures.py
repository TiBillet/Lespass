"""
Exporter puis supprimer les anciennes clôtures, la nuit de la bascule.
/ Export then delete the old closures, on the switch-over night.

LOCALISATION : tests/pytest/test_anciennes_clotures.py

RÈGLES MÉTIER TESTÉES
Fiche : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-reprise-ventes.md (§1, §12 étapes 4
et 7), brief : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-briefs/05-R-4a.md.
- `manage.py anciennes_clotures --exporter <dossier>` lit les clôtures de chaque lieu et
  écrit UN fichier JSON par lieu (`<schéma>.json`, liste des lignes) et un `resume.csv`
  (schéma, domaine principal, nombre de clôtures). Un lieu sans clôture n'a pas de
  fichier, mais une ligne à 0 dans le résumé. Aucune écriture en base.
- Un dossier qui contient déjà un fichier est refusé (`CommandError`) : rien n'est écrasé.
- `manage.py anciennes_clotures --supprimer --export <dossier>` compare, pour chaque lieu,
  le nombre de clôtures en base au nombre du `resume.csv`. Égal : les clôtures du lieu sont
  supprimées. Différent, ou lieu absent du résumé : rien n'est supprimé pour ce lieu, il
  est listé en refus. Sans `--executer`, passage à blanc : rien n'est supprimé.
/ Business rules: one JSON file per venue plus a summary; non-empty folder refused; delete
only when the database count equals the summary count; dry run without --executer.

CONTRAT LU PAR CES TESTS (le brief ne donne pas les noms de colonnes : ils sont regroupés
dans les constantes ci-dessous pour être changés en un seul endroit)
- Appel : `call_command("anciennes_clotures", "--exporter", <dossier>)` et
  `call_command("anciennes_clotures", "--supprimer", "--export", <dossier>[, "--executer"])`.
- `resume.csv` : UTF-8, séparateur virgule, une ligne d'en-tête, colonnes `schema`,
  `domaine`, `nombre_de_clotures`.
- Un lieu refusé est cité par son domaine principal dans la sortie de la commande.
/ Contract: CLI arguments, summary columns, refused venue named by its primary domain.

SIMULATIONS
- AUCUN marqueur `django_db` : la commande ouvre ses propres transactions et les valide ;
  c'est ce qu'on veut prouver. Il n'y a donc pas d'annulation automatique en fin de test.
- Chaque lieu est un lieu JETABLE `test_clotures_*`, copié du schéma modèle `test_modele`
  (tests/pytest/schemas_clones.py), avec sa ligne `Client` et son domaine principal écrits
  par `bulk_create()`. Il est supprimé en fin de test, même en échec, en SQL brut.
- La base de dev contient d'autres lieux, que la commande lit aussi. Les tests de
  suppression écrivent donc eux-mêmes un `resume.csv` qui ne cite QUE leurs lieux jetables :
  tout autre lieu est absent du résumé, donc refusé, donc intact.
- Les clôtures sont écrites par `bulk_create()` : aucun signal, aucun calcul.
/ No django_db: the command commits. Disposable venues, deleted in raw SQL. The delete
tests write their own summary naming only their venues, so every other venue is refused.

Lancer / Run : make test ARGS="tests/pytest/test_anciennes_clotures.py"
"""

import csv
import json
import os
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone
from django_tenants.utils import tenant_context

import schemas_clones
from comptabilite.models import ClotureCaisse
from Customers.models import Client, Domain

# --------------------------------------------------------------------------
# Constantes : la commande et son contrat
# / Constants: the command and its contract
# --------------------------------------------------------------------------

NOM_DE_LA_COMMANDE = "anciennes_clotures"
NOM_DU_RESUME = "resume.csv"

COLONNE_SCHEMA = "schema"
COLONNE_DOMAINE = "domaine"
COLONNE_NOMBRE = "nombre_de_clotures"

# Préfixe de tout ce que ces tests créent et suppriment. Le nettoyage refuse tout autre nom.
# / Prefix of everything these tests create and delete.
PREFIXE_DES_LIEUX_JETABLES = "test_clotures_"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def schema_modele_a_jour():
    """
    Garde-fou (DEBUG=1 et TEST=1 dans l'environnement du conteneur, jamais
    `settings.DEBUG` que pytest-django force à False), puis schéma modèle prêt.
    / Safety check, then the template schema is ready.
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
def schemas_crees():
    """
    La liste des schémas jetables du test. En fin de test, même en échec, ils sont
    supprimés en SQL brut, avec leur domaine et leur ligne `Client`.
    / List of the test's disposable schemas, dropped at the end even on failure.
    """
    connection.set_schema_to_public()
    liste_des_schemas = []
    try:
        yield liste_des_schemas
    finally:
        connection.set_schema_to_public()
        with connection.cursor() as curseur:
            for nom_du_schema in liste_des_schemas:
                if not nom_du_schema.startswith(PREFIXE_DES_LIEUX_JETABLES):
                    raise RuntimeError(f"Nettoyage refusé pour « {nom_du_schema} »")
                curseur.execute(f'DROP SCHEMA IF EXISTS "{nom_du_schema}" CASCADE')
                curseur.execute(
                    'DELETE FROM "Customers_domain" WHERE tenant_id IN '
                    '(SELECT uuid FROM "Customers_client" WHERE schema_name = %s)',
                    [nom_du_schema],
                )
                curseur.execute(
                    'DELETE FROM "Customers_client" WHERE schema_name = %s',
                    [nom_du_schema],
                )


# --------------------------------------------------------------------------
# Outils des tests
# / Test helpers
# --------------------------------------------------------------------------


def creer_un_lieu_avec_des_clotures(schemas_crees, nombre_de_clotures):
    """
    Crée un lieu jetable (schéma copié, `Client`, domaine principal) qui contient
    `nombre_de_clotures` clôtures journalières, sans calcul (`bulk_create`).
    / Creates a disposable venue holding the given number of daily closures.

    :return: SimpleNamespace(client, nom_du_schema, domaine)
    """
    identifiant = uuid.uuid4().hex[:8]
    nom_du_schema = f"{PREFIXE_DES_LIEUX_JETABLES}{identifiant}"
    domaine = f"test-clotures-{identifiant}.tibillet.localhost"

    schemas_crees.append(nom_du_schema)
    schemas_clones.creer_le_schema_par_clonage(nom_du_schema)

    client_du_lieu = Client(
        schema_name=nom_du_schema,
        name=f"Test clotures {identifiant}",
        categorie=Client.SALLE_SPECTACLE,
    )
    Client.objects.bulk_create([client_du_lieu])
    Domain.objects.bulk_create(
        [Domain(domain=domaine, tenant=client_du_lieu, is_primary=True)]
    )

    lieu = SimpleNamespace(
        client=client_du_lieu, nom_du_schema=nom_du_schema, domaine=domaine
    )
    ajouter_des_clotures(lieu, nombre_de_clotures)
    return lieu


def ajouter_des_clotures(lieu, nombre_de_clotures):
    """
    Ajoute des clôtures journalières au lieu. Chaque clôture a sa journée et un numéro
    séquentiel qui suit le dernier du lieu (contraintes d'unicité).
    / Adds daily closures to the venue, one day each, following sequence numbers.
    """
    premiere_heure = timezone.now() - timedelta(days=1000)
    with tenant_context(lieu.client):
        numero_deja_utilise = ClotureCaisse.objects.count()
        clotures_a_ecrire = []
        for position in range(nombre_de_clotures):
            numero = numero_deja_utilise + position + 1
            debut = premiere_heure + timedelta(days=numero)
            clotures_a_ecrire.append(
                ClotureCaisse(
                    niveau=ClotureCaisse.NIVEAU_JOURNALIER,
                    numero_sequentiel=numero,
                    datetime_debut=debut,
                    datetime_fin=debut + timedelta(days=1),
                    rapport_json={"en_tete": {"ancien_format": True}},
                )
            )
        ClotureCaisse.objects.bulk_create(clotures_a_ecrire)
    connection.set_schema_to_public()


def compter_les_clotures(lieu):
    """
    Le nombre de clôtures du lieu en base, en SQL brut.
    / Number of closures of the venue in the database, raw SQL.
    """
    connection.set_schema_to_public()
    with connection.cursor() as curseur:
        curseur.execute(
            f'SELECT count(*) FROM "{lieu.nom_du_schema}".comptabilite_cloturecaisse'
        )
        return curseur.fetchone()[0]


def ecrire_un_resume(dossier, lieux_et_nombres):
    """
    Écrit un `resume.csv` qui ne cite que les lieux donnés.
    / Writes a summary naming only the given venues.

    :param lieux_et_nombres: liste de couples (lieu, nombre de clôtures annoncé)
    """
    with open(dossier / NOM_DU_RESUME, "w", newline="", encoding="utf-8") as fichier:
        ecrivain = csv.writer(fichier)
        ecrivain.writerow([COLONNE_SCHEMA, COLONNE_DOMAINE, COLONNE_NOMBRE])
        for lieu, nombre_annonce in lieux_et_nombres:
            ecrivain.writerow([lieu.nom_du_schema, lieu.domaine, nombre_annonce])


def lire_le_resume(dossier):
    """
    Le résumé sous forme de dictionnaire : schéma -> ligne.
    / The summary as a dictionary: schema -> row.
    """
    lignes_par_schema = {}
    with open(dossier / NOM_DU_RESUME, newline="", encoding="utf-8") as fichier:
        for ligne in csv.DictReader(fichier):
            lignes_par_schema[ligne[COLONNE_SCHEMA]] = ligne
    return lignes_par_schema


def lancer_la_commande(*arguments):
    """
    Lance la commande et rend sa sortie.
    / Runs the command and returns its output.
    """
    sortie = StringIO()
    call_command(NOM_DE_LA_COMMANDE, *arguments, stdout=sortie, stderr=sortie)
    return sortie.getvalue()


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_export_un_fichier_par_lieu_et_le_resume(tmp_path, schemas_crees):
    """
    Un lieu avec 2 clôtures a son fichier JSON (2 lignes) ; un lieu sans clôture n'a pas
    de fichier mais une ligne à 0 dans le résumé.
    / A venue with 2 closures gets a JSON file; a venue with none gets no file, a 0 row.
    """
    lieu_avec_clotures = creer_un_lieu_avec_des_clotures(schemas_crees, 2)
    lieu_sans_cloture = creer_un_lieu_avec_des_clotures(schemas_crees, 0)

    lancer_la_commande("--exporter", str(tmp_path))

    fichier_du_lieu = tmp_path / f"{lieu_avec_clotures.nom_du_schema}.json"
    assert fichier_du_lieu.exists()
    lignes_exportees = json.loads(fichier_du_lieu.read_text(encoding="utf-8"))
    assert len(lignes_exportees) == 2
    numeros_exportes = sorted(ligne["numero_sequentiel"] for ligne in lignes_exportees)
    assert numeros_exportes == [1, 2]

    assert not (tmp_path / f"{lieu_sans_cloture.nom_du_schema}.json").exists()

    resume = lire_le_resume(tmp_path)
    ligne_du_lieu_avec = resume[lieu_avec_clotures.nom_du_schema]
    assert ligne_du_lieu_avec[COLONNE_DOMAINE] == lieu_avec_clotures.domaine
    assert ligne_du_lieu_avec[COLONNE_NOMBRE] == "2"
    ligne_du_lieu_sans = resume[lieu_sans_cloture.nom_du_schema]
    assert ligne_du_lieu_sans[COLONNE_DOMAINE] == lieu_sans_cloture.domaine
    assert ligne_du_lieu_sans[COLONNE_NOMBRE] == "0"


def test_export_n_ecrit_rien_en_base(tmp_path, schemas_crees):
    """
    Après l'export, les clôtures du lieu sont toujours là, en même nombre.
    / After the export, the venue's closures are all still there.
    """
    lieu = creer_un_lieu_avec_des_clotures(schemas_crees, 3)

    lancer_la_commande("--exporter", str(tmp_path))

    assert compter_les_clotures(lieu) == 3


def test_export_refuse_un_dossier_deja_rempli(tmp_path, schemas_crees):
    """
    Un dossier qui contient déjà un fichier est refusé : le fichier reste tel quel et la
    commande n'écrit rien d'autre.
    / A folder already holding a file is refused: nothing is overwritten or added.
    """
    creer_un_lieu_avec_des_clotures(schemas_crees, 1)
    fichier_deja_la = tmp_path / "deja_la.txt"
    fichier_deja_la.write_text("à garder", encoding="utf-8")

    with pytest.raises(CommandError) as erreur_levee:
        lancer_la_commande("--exporter", str(tmp_path))

    # Le refus vient de la commande elle-même, pas d'une commande introuvable.
    # / The refusal comes from the command itself, not from a missing command.
    assert "Unknown command" not in str(erreur_levee.value)
    assert fichier_deja_la.read_text(encoding="utf-8") == "à garder"
    assert sorted(fichier.name for fichier in tmp_path.iterdir()) == ["deja_la.txt"]


def test_suppression_a_blanc_ne_supprime_rien(tmp_path, schemas_crees):
    """
    Sans `--executer`, les nombres collent mais rien n'est supprimé.
    / Without --executer the counts match but nothing is deleted.
    """
    lieu = creer_un_lieu_avec_des_clotures(schemas_crees, 2)
    ecrire_un_resume(tmp_path, [(lieu, 2)])

    lancer_la_commande("--supprimer", "--export", str(tmp_path))

    assert compter_les_clotures(lieu) == 2


def test_suppression_quand_les_nombres_collent(tmp_path, schemas_crees):
    """
    Avec `--executer`, le lieu dont le nombre de clôtures égale celui du résumé est vidé.
    Un autre lieu, déjà cité au résumé avec le bon nombre, l'est aussi (une transaction
    chacun).
    / With --executer, a venue whose count equals the summary is emptied.
    """
    lieu_a_vider = creer_un_lieu_avec_des_clotures(schemas_crees, 2)
    autre_lieu_a_vider = creer_un_lieu_avec_des_clotures(schemas_crees, 1)
    ecrire_un_resume(tmp_path, [(lieu_a_vider, 2), (autre_lieu_a_vider, 1)])

    lancer_la_commande("--supprimer", "--export", str(tmp_path), "--executer")

    assert compter_les_clotures(lieu_a_vider) == 0
    assert compter_les_clotures(autre_lieu_a_vider) == 0


def test_suppression_refusee_si_le_nombre_differe(tmp_path, schemas_crees):
    """
    Le résumé annonce 2 clôtures, la base en a 3 : rien n'est supprimé pour ce lieu, et
    il est cité (par son domaine) dans la sortie. Un lieu dont le nombre colle est vidé
    quand même : le refus est par lieu.
    / Summary says 2, database holds 3: nothing deleted, the venue is named in the output.
    """
    lieu_qui_differe = creer_un_lieu_avec_des_clotures(schemas_crees, 2)
    lieu_qui_colle = creer_un_lieu_avec_des_clotures(schemas_crees, 1)
    ecrire_un_resume(tmp_path, [(lieu_qui_differe, 2), (lieu_qui_colle, 1)])
    # Une clôture arrive après l'export : 3 en base, 2 au résumé.
    # / A closure appears after the export: 3 in the database, 2 in the summary.
    ajouter_des_clotures(lieu_qui_differe, 1)

    sortie = lancer_la_commande("--supprimer", "--export", str(tmp_path), "--executer")

    assert compter_les_clotures(lieu_qui_differe) == 3
    assert lieu_qui_differe.domaine in sortie
    assert compter_les_clotures(lieu_qui_colle) == 0


def test_suppression_refusee_si_le_lieu_manque_au_resume(tmp_path, schemas_crees):
    """
    Un lieu absent du résumé n'est pas supprimé, même avec `--executer`, et il est cité
    (par son domaine) dans la sortie.
    / A venue missing from the summary is not deleted, and is named in the output.
    """
    lieu_absent_du_resume = creer_un_lieu_avec_des_clotures(schemas_crees, 2)
    lieu_present_au_resume = creer_un_lieu_avec_des_clotures(schemas_crees, 1)
    ecrire_un_resume(tmp_path, [(lieu_present_au_resume, 1)])

    sortie = lancer_la_commande("--supprimer", "--export", str(tmp_path), "--executer")

    assert compter_les_clotures(lieu_absent_du_resume) == 2
    assert lieu_absent_du_resume.domaine in sortie
    assert compter_les_clotures(lieu_present_au_resume) == 0
