"""
L'archive fiscale LNE lit les ventes, la vérification d'intégrité lit leurs chaînes,
et les anciennes clôtures de la caisse ne s'écrivent plus.
/ The LNE fiscal archive reads the sales, the integrity check reads their chains, and
the register's old closures are no longer written.

LOCALISATION : tests/pytest/test_archive_lne_ventes.py

RÈGLE MÉTIER TESTÉE — L'ARCHIVE FISCALE (`laboutik/archivage.py`)
L'archive exporte les ventes réglées du lieu, de TOUTES les origines (caisse, tireuse,
en ligne…), en quatre fichiers CSV :
- `ventes.csv` : l'en-tête de chaque vente (numéro, nature, origine, totaux) et son
  empreinte (`previous_hmac`, `hmac_hash`) ;
- `articles.csv` : les articles de chaque vente, avec le HT et la TVA STOCKÉS sur
  l'article (`total_ht`, `total_tva`), jamais recalculés depuis `amount × qty` ;
- `reglements.csv` : les règlements de chaque vente (moyen, montant) ;
- `clotures.csv` : les clôtures uniques du lieu (`comptabilite.ClotureCaisse`), jamais
  les anciennes (`laboutik.ClotureCaisse`).
Une correction de moyen de paiement est une vente « CORRECTION » (deux règlements qui
s'annulent) : elle est dans ces fichiers, sans fichier `corrections.csv` à part. Le
README de l'archive décrit ces fichiers.
/ The archive exports the venue's settled sales, from every origin, in four CSV files
with the STORED HT and VAT. A payment correction is a CORRECTION sale, with no
corrections.csv. The README describes the files.

RÈGLE MÉTIER TESTÉE — LA VÉRIFICATION D'INTÉGRITÉ
`manage.py verify_integrity` vérifie la chaîne des ventes (`verifier_chaine_ventes`) et
la chaîne des clôtures. `verify_integrity` et `verify_clotures` sortent avec un code
différent de 0 quand ils trouvent une anomalie : une tâche planifiée ou un script voit
l'alerte sans lire le texte.
/ verify_integrity checks the sales chain and the closures chain. Both commands exit
with a non-zero code on an anomaly.

RÈGLE MÉTIER TESTÉE — LE BOUTON « EXPORT FISCAL »
La liste des clôtures uniques de l'admin (`comptabilite/admin.py`) porte le bouton
« Export fiscal » dans son bandeau : il ouvre le formulaire de l'export.
/ The single closures list carries the "Fiscal export" button in its banner.

RÈGLE MÉTIER TESTÉE — PLUS AUCUNE ANCIENNE CLÔTURE ÉCRITE
- Les tâches de clôture de la caisse jamais planifiées (`laboutik/tasks.py`) n'existent
  plus : ni dans le module, ni dans le registre de Celery, ni dans le planning
  (`TiBillet/celery.py`), ni chez un appelant.
- Aucun code de production n'écrit une `laboutik.ClotureCaisse`. Seuls l'admin de
  l'ancienne clôture (consultation jusqu'à son retrait) et les migrations la citent.
/ The never-scheduled register closure tasks are gone. No production code writes an
old closure.

SCHÉMA DÉDIÉ
L'archive et les commandes lisent TOUTES les ventes et clôtures du lieu : il faut un
lieu qui ne contient que celles du test (`FastTenantTestCase`). Chaque test annule sa
transaction à la fin. Le singleton `LaboutikConfiguration` est créé en base
(tests/PIEGES.md 9.86) : il porte la clé des empreintes. La `Configuration` du lieu est
réécrite à chaque test : son cache (django-solo) survit à l'annulation.
Les ventes sont écrites PAR LE SERVICE (`fabriques_vente.py`, `services_vente.py`),
jamais à la main. Les J sont créées par la vraie tâche
(`comptabilite.tasks.generer_cloture_pour_tenant`).
/ Dedicated schema, rolled back after each test. Sales through the sale service, J
through the real task.

D'OÙ VIENNENT LES VALEURS ATTENDUES (calculées à la main)
Trois jus à 3,50 € (TVA 20 %), 10,50 €, payés 5,00 € en monnaie locale et 5,50 € par
carte bancaire (tronc CHANTIER-05-montants-entiers.md §5). Pendant la transition, la
ligne est coupée en deux « parts », chacune avec son argent réel :
- part monnaie locale : TTC 500, HT = arrondi(500 / 1,2 = 416,67) = 417, TVA 83 ;
- part carte bancaire : TTC 550, HT = arrondi(550 / 1,2 = 458,33) = 458, TVA 92 ;
- vente : TTC 1050, HT 875, TVA 175.
Une TVA recalculée depuis `amount × qty` donnerait int(350 × 1,428571) − 417 =
499 − 417 = 82, d'où 82 + 92 = 174 au lieu de 175 : l'archive lit la TVA stockée.
/ Three 3.50 € juices paid 5.00 € local currency + 5.50 € card: parts 417/83 and
458/92, sale 875/175. A VAT recomputed from amount × qty would give 174.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-G-lecteurs.md (§2, §5
tests 4, 5 et 6) ; CHANTIER-05-SUIVI.md (tâches de clôture mortes, archive sans
corrections.csv).

Lancer / Run : make test ARGS="tests/pytest/test_archive_lne_ventes.py"
"""

import sys

# Le code Django vit dans /DjangoFiles a l'interieur du conteneur.
# / Django code lives in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django  # noqa: E402

django.setup()

import csv  # noqa: E402
import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import uuid  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402
from datetime import timezone as fuseau_horaire_python  # noqa: E402
from decimal import Decimal  # noqa: E402
from io import StringIO  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.apps import apps  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.core.management.base import CommandError  # noqa: E402
from django.db import connection  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from django_tenants.test.cases import FastTenantTestCase  # noqa: E402
from django_tenants.test.client import TenantClient  # noqa: E402

import comptabilite.tasks  # noqa: E402
from AuthBillet.models import TibilletUser  # noqa: E402
from BaseBillet.models import (  # noqa: E402
    Configuration,
    LigneArticle,
    PaymentMethod,
    SaleOrigin,
)
from BaseBillet.models_vente import Vente  # noqa: E402
from BaseBillet.services_vente import (  # noqa: E402
    ajouter_article,
    ajouter_reglement,
    encaisser_vente,
    ouvrir_vente,
)
from comptabilite.models import ClotureCaisse  # noqa: E402
from Customers.models import Client  # noqa: E402
from fabriques_ecran import attributs_des_elements  # noqa: E402
from fabriques_vente import (  # noqa: E402
    creer_tarif_vendu,
    fabriquer_vente_encaissee,
    verifier_egalites,
)
from laboutik.archivage import (  # noqa: E402
    calculer_hash_fichiers,
    empaqueter_zip,
    generer_fichiers_archive,
    generer_readme_fiscal,
    verifier_hash_archive,
)
from laboutik.models import LaboutikConfiguration, PointDeVente  # noqa: E402
from laboutik.models import ClotureCaisse as AncienneClotureCaisse  # noqa: E402

# Les quatre fichiers des ventes et des clôtures, et le fichier retiré.
# / The four sales and closures files, and the removed file.
FICHIERS_DES_VENTES_ET_DES_CLOTURES = [
    "ventes.csv",
    "articles.csv",
    "reglements.csv",
    "clotures.csv",
]
FICHIER_DES_CORRECTIONS_RETIRE = "corrections.csv"

# Les colonnes de chaque fichier, dans l'ordre : le contrat de l'archive, décrit dans
# le dossier LNE. Une colonne ajoutée, retirée ou déplacée doit se voir.
# / Each file's columns, in order: the archive contract.
COLONNES_ATTENDUES_PAR_FICHIER = {
    "ventes.csv": [
        "uuid", "numero", "nature", "statut", "origine", "unite",
        "datetime_encaissement", "point_de_vente", "point_de_vente_uuid",
        "operateur_email", "vente_liee_uuid", "total_catalogue", "total_offert",
        "total_ttc", "total_ht", "total_tva", "previous_hmac", "hmac_hash",
    ],
    "articles.csv": [
        "uuid", "vente_uuid", "vente_numero", "datetime", "article", "categorie",
        "pricesold_uuid", "uuid_transaction", "quantite", "prix_unitaire",
        "taux_tva", "total_catalogue", "part_offerte", "source_offert",
        "part_en_jetons", "total_ttc", "total_ht", "total_tva",
        "hors_chiffre_affaires",
    ],
    "reglements.csv": [
        "uuid", "vente_uuid", "vente_numero", "moyen", "montant", "asset", "carte",
        "fedow_transaction_uuid", "reference_externe", "datetime",
    ],
    "clotures.csv": [
        "uuid", "niveau", "numero_sequentiel", "datetime_debut", "datetime_fin",
        "numero_premiere_vente", "numero_derniere_vente",
        "empreinte_de_la_derniere_vente", "total_general",
        "total_ht", "total_tva", "total_argent_recu", "nombre_transactions",
        "total_perpetuel", "nombre_ventes_perpetuel", "responsable_email",
        "point_de_vente", "rapport_json", "previous_hmac", "hmac_hash",
    ],
}

# Les fichiers de production qui ont le droit de citer l'ancienne clôture
# (`laboutik.ClotureCaisse`) : son admin, la caisse (lectures de l'ancien moteur et
# du temps réel), la commande de démo (lecture), le stock (FK morte) et le modèle.
# Tous partent avec le modèle. Un nouveau fichier qui la cite fait échouer le test.
# / Production files allowed to cite the old closure; a new one fails the test.
FICHIERS_QUI_PEUVENT_CITER_L_ANCIENNE_CLOTURE = {
    Path("Administration/admin/laboutik.py"),
    Path("laboutik/views.py"),
    Path("laboutik/management/commands/create_test_pos_data.py"),
    Path("inventaire/models.py"),
    Path("laboutik/models.py"),
}

# Les tâches de clôture de la caisse jamais planifiées, retirées de laboutik/tasks.py.
# / The never-scheduled register closure tasks, removed from laboutik/tasks.py.
NOMS_DES_TACHES_DE_CLOTURE_RETIREES = [
    "generer_cloture_journaliere_auto",
    "generer_cloture_hebdomadaire",
    "generer_cloture_mensuelle",
    "generer_cloture_annuelle",
    "_generer_cloture_agregee",
    "envoyer_rapports_clotures_recentes",
]

# Le seul fichier de production qui peut encore citer l'ancienne clôture pour l'écrire :
# son admin, consulté jusqu'au retrait du modèle. Les migrations sont exclues à part.
# / The only production file still allowed to cite the old closure: its admin.
FICHIER_DE_L_ADMIN_DE_L_ANCIENNE_CLOTURE = Path("Administration/admin/laboutik.py")

# Les dossiers qui ne sont pas du code de production.
# / Folders that are not production code.
DOSSIERS_HORS_PRODUCTION = {"tests", "migrations", "__pycache__"}


# ---------------------------------------------------------------------- #
#  Outils de lecture                                                      #
#  / Reading helpers                                                      #
# ---------------------------------------------------------------------- #


def lignes_du_csv(contenu_du_fichier):
    """
    Les lignes d'un CSV de l'archive, en dictionnaires {colonne: valeur}.
    L'archive écrit en UTF-8 avec BOM, délimiteur « ; ».
    / The rows of an archive CSV, as dicts. UTF-8 with BOM, ";" delimiter.
    """
    texte_du_fichier = contenu_du_fichier.decode("utf-8-sig")
    lecteur = csv.DictReader(texte_du_fichier.splitlines(), delimiter=";")
    return list(lecteur)


def colonnes_du_csv(contenu_du_fichier):
    """
    Les noms des colonnes d'un CSV de l'archive (sa première ligne).
    / The column names of an archive CSV (its first row).
    """
    texte_du_fichier = contenu_du_fichier.decode("utf-8-sig")
    lecteur = csv.reader(texte_du_fichier.splitlines(), delimiter=";")
    return next(lecteur)


def lignes_dont_la_colonne_vaut(lignes, nom_de_la_colonne, valeur_cherchee):
    """
    Les lignes du CSV dont la colonne vaut la valeur cherchée.
    / The CSV rows whose column holds the searched value.
    """
    lignes_trouvees = []
    for ligne in lignes:
        if ligne[nom_de_la_colonne] == valeur_cherchee:
            lignes_trouvees.append(ligne)
    return lignes_trouvees


def lancer_la_commande(nom_de_la_commande, *arguments):
    """
    Lance une commande de gestion et rend (texte écrit, code de sortie).
    Une commande qui signale une anomalie par `CommandError` sort avec son
    `returncode` (1 par défaut) ; par `sys.exit(n)`, avec n. Sans erreur : 0.
    / Runs a management command, returns (written text, exit code).
    """
    sortie_de_la_commande = StringIO()
    erreurs_de_la_commande = StringIO()
    code_de_sortie = 0
    try:
        call_command(
            nom_de_la_commande,
            *arguments,
            stdout=sortie_de_la_commande,
            stderr=erreurs_de_la_commande,
        )
    except CommandError as erreur_de_la_commande:
        code_de_sortie = erreur_de_la_commande.returncode
        erreurs_de_la_commande.write(str(erreur_de_la_commande))
    except SystemExit as sortie_du_programme:
        code_de_sortie = sortie_du_programme.code
    texte_ecrit = sortie_de_la_commande.getvalue() + erreurs_de_la_commande.getvalue()
    return texte_ecrit, code_de_sortie


def dossiers_du_code_de_production():
    """
    Les dossiers du code de production : chaque application Django du dépôt, plus le
    paquet du projet (`TiBillet`). Les applications installées depuis `.venv` ne sont
    pas du code du dépôt.
    / Production code folders: each Django app of the repository, plus the project
    package. Apps installed from .venv are not repository code.
    """
    racine_du_depot = Path(settings.BASE_DIR)
    dossiers = [racine_du_depot / "TiBillet"]
    for configuration_de_l_application in apps.get_app_configs():
        dossier_de_l_application = Path(configuration_de_l_application.path)
        application_du_depot = dossier_de_l_application.parent == racine_du_depot
        if application_du_depot and dossier_de_l_application not in dossiers:
            dossiers.append(dossier_de_l_application)
    return dossiers


def fichiers_python_de_production():
    """
    Les fichiers Python du code de production, sans les tests ni les migrations.
    Rend des chemins relatifs à la racine du dépôt.
    / Production Python files, without tests or migrations, relative to the repo root.
    """
    racine_du_depot = Path(settings.BASE_DIR)
    fichiers = []
    dossiers = dossiers_du_code_de_production()
    for dossier in dossiers:
        chemins_du_dossier = sorted(dossier.rglob("*.py"))
        for chemin in chemins_du_dossier:
            chemin_relatif = chemin.relative_to(racine_du_depot)
            if set(chemin_relatif.parts) & DOSSIERS_HORS_PRODUCTION:
                continue
            fichiers.append(chemin_relatif)
    return fichiers


# Un import de l'ancienne clôture : `from laboutik.models import ... ClotureCaisse`,
# sur une ligne ou entre parenthèses, avec un éventuel alias (`as ...`).
# / An import of the old closure, on one line or in parentheses, maybe aliased.
IMPORT_DEPUIS_LES_MODELES_DE_LA_CAISSE = re.compile(
    r"from\s+laboutik\.models\s+import\s+(\([^)]*\)|[^\n]*)"
)
NOM_DE_L_ANCIENNE_CLOTURE_IMPORTEE = re.compile(r"\bClotureCaisse\b(?:\s+as\s+(\w+))?")


def noms_locaux_de_l_ancienne_cloture(source_du_fichier):
    """
    Les noms sous lesquels un fichier importe `laboutik.models.ClotureCaisse`
    (« ClotureCaisse », ou son alias). Vide si le fichier ne l'importe pas.
    / The names under which a file imports the old closure (name or alias).
    """
    noms_locaux = []
    imports_trouves = IMPORT_DEPUIS_LES_MODELES_DE_LA_CAISSE.findall(source_du_fichier)
    for noms_importes in imports_trouves:
        correspondances = NOM_DE_L_ANCIENNE_CLOTURE_IMPORTEE.finditer(noms_importes)
        for correspondance in correspondances:
            nom_local = correspondance.group(1) or "ClotureCaisse"
            # Un fichier peut importer le modèle plusieurs fois (imports locaux) : le
            # nom n'est gardé qu'une fois.
            # / A file may import the model several times: each name is kept once.
            if nom_local not in noms_locaux:
                noms_locaux.append(nom_local)
    return noms_locaux


def ecritures_de_l_ancienne_cloture(source_du_fichier, nom_local):
    """
    Les écritures d'une ancienne clôture dans un fichier : création (`create`,
    `bulk_create`, `get_or_create`, `update_or_create`), verrou d'écriture
    (`select_for_update`) ou construction (`ClotureCaisse(...)`). Rend les numéros de
    ligne.
    / Writes of an old closure in a file: creation, write lock or construction.
    Returns the line numbers.
    """
    motif_des_ecritures = re.compile(
        rf"\b{nom_local}\.objects\.(?:create|bulk_create|get_or_create|"
        rf"update_or_create|select_for_update)\(|\b{nom_local}\("
    )
    numeros_de_ligne = []
    for correspondance in motif_des_ecritures.finditer(source_du_fichier):
        numero_de_ligne = source_du_fichier[: correspondance.start()].count("\n") + 1
        numeros_de_ligne.append(numero_de_ligne)
    return numeros_de_ligne


def _uuid_d_une_ligne_du_csv(ligne_du_csv):
    """La clé de tri d'une ligne de CSV : son uuid. / Sort key: the row's uuid."""
    return ligne_du_csv["uuid"]


def empreinte_recalculee_depuis_l_archive(
    ligne_de_la_vente, articles_de_la_vente, reglements_de_la_vente, cle
):
    """
    Recalcule l'empreinte d'une vente à partir des SEULS fichiers de l'archive et de
    la clé du lieu, avec le message décrit dans le README de l'archive (le message de
    `laboutik/integrity.py` `calculer_hmac_vente`, réécrit ici à la main) : un JSON
    canonique, articles et règlements triés par uuid, l'heure d'encaissement en UTC.
    / Recomputes a sale's fingerprint from the archive files and the key only, with
    the message described in the archive README.

    :param ligne_de_la_vente: la ligne de la vente dans `ventes.csv`
    :param articles_de_la_vente: ses lignes de `articles.csv`
    :param reglements_de_la_vente: ses lignes de `reglements.csv`
    :param cle: la clé HMAC du lieu, en clair
    :return: l'empreinte (64 caractères hexadécimaux)
    """
    articles_tries = sorted(articles_de_la_vente, key=_uuid_d_une_ligne_du_csv)
    articles_du_message = []
    for article in articles_tries:
        articles_du_message.append([
            article["uuid"],
            article["pricesold_uuid"],
            f"{Decimal(article['quantite']):.6f}",
            int(article["prix_unitaire"]),
            f"{Decimal(article['taux_tva']):.2f}",
            int(article["total_catalogue"]),
            int(article["part_offerte"]),
            article["source_offert"],
            int(article["part_en_jetons"]),
            int(article["total_ttc"]),
            int(article["total_ht"]),
            int(article["total_tva"]),
            article["hors_chiffre_affaires"] == "True",
        ])

    reglements_tries = sorted(reglements_de_la_vente, key=_uuid_d_une_ligne_du_csv)
    reglements_du_message = []
    for reglement in reglements_tries:
        reglements_du_message.append([
            reglement["uuid"],
            reglement["moyen"],
            int(reglement["montant"]),
            reglement["asset"],
            reglement["carte"],
            reglement["fedow_transaction_uuid"],
            reglement["reference_externe"],
        ])

    heure_d_encaissement_en_utc = datetime.fromisoformat(
        ligne_de_la_vente["datetime_encaissement"]
    ).astimezone(fuseau_horaire_python.utc)
    donnees = {
        "format": 1,
        "uuid": ligne_de_la_vente["uuid"],
        "numero": int(ligne_de_la_vente["numero"]),
        "datetime_encaissement": heure_d_encaissement_en_utc.isoformat(),
        "nature": ligne_de_la_vente["nature"],
        "origine": ligne_de_la_vente["origine"],
        "unite": ligne_de_la_vente["unite"],
        "statut": ligne_de_la_vente["statut"],
        "point_de_vente": ligne_de_la_vente["point_de_vente_uuid"],
        "vente_liee": ligne_de_la_vente["vente_liee_uuid"],
        "totaux": [
            int(ligne_de_la_vente["total_catalogue"]),
            int(ligne_de_la_vente["total_offert"]),
            int(ligne_de_la_vente["total_ttc"]),
            int(ligne_de_la_vente["total_ht"]),
            int(ligne_de_la_vente["total_tva"]),
        ],
        "articles": articles_du_message,
        "reglements": reglements_du_message,
        "previous_hmac": ligne_de_la_vente["previous_hmac"],
    }
    message = json.dumps(
        donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hmac.new(
        cle.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _numero_ou_rien(texte_du_numero):
    """
    Un numéro lu dans le CSV : un entier, ou None si la cellule est vide.
    / A number read from the CSV: an int, or None when the cell is empty.
    """
    if texte_du_numero == "":
        return None
    return int(texte_du_numero)


def empreinte_de_la_cloture_recalculee_depuis_l_archive(ligne_de_la_cloture, cle):
    """
    Recalcule l'empreinte d'une clôture à partir de SA SEULE ligne de `clotures.csv`
    et de la clé du lieu, avec le message décrit dans le README de l'archive (celui
    de `comptabilite/integrite.py` `calculer_hmac_cloture`, réécrit ici à la main) :
    un JSON canonique, les bornes en UTC, le rapport relu depuis sa colonne.
    / Recomputes a closure's fingerprint from its clotures.csv row and the key only,
    with the message described in the archive README.

    :param ligne_de_la_cloture: la ligne de la clôture dans `clotures.csv`
    :param cle: la clé HMAC du lieu, en clair
    :return: l'empreinte (64 caractères hexadécimaux)
    """
    debut_en_utc = datetime.fromisoformat(
        ligne_de_la_cloture["datetime_debut"]
    ).astimezone(fuseau_horaire_python.utc)
    fin_en_utc = datetime.fromisoformat(
        ligne_de_la_cloture["datetime_fin"]
    ).astimezone(fuseau_horaire_python.utc)
    donnees = {
        "format": 1,
        "niveau": ligne_de_la_cloture["niveau"],
        "numero_sequentiel": int(ligne_de_la_cloture["numero_sequentiel"]),
        "datetime_debut": debut_en_utc.isoformat(),
        "datetime_fin": fin_en_utc.isoformat(),
        "numero_premiere_vente": _numero_ou_rien(
            ligne_de_la_cloture["numero_premiere_vente"]
        ),
        "numero_derniere_vente": _numero_ou_rien(
            ligne_de_la_cloture["numero_derniere_vente"]
        ),
        "empreinte_de_la_derniere_vente": ligne_de_la_cloture[
            "empreinte_de_la_derniere_vente"
        ],
        "totaux": {
            "total_general": int(ligne_de_la_cloture["total_general"]),
            "total_ht": int(ligne_de_la_cloture["total_ht"]),
            "total_tva": int(ligne_de_la_cloture["total_tva"]),
            "total_argent_recu": int(ligne_de_la_cloture["total_argent_recu"]),
            "nombre_transactions": int(ligne_de_la_cloture["nombre_transactions"]),
        },
        "perpetuels": {
            "total_perpetuel": int(ligne_de_la_cloture["total_perpetuel"]),
            "nombre_ventes_perpetuel": int(
                ligne_de_la_cloture["nombre_ventes_perpetuel"]
            ),
        },
        "rapport_json": json.loads(ligne_de_la_cloture["rapport_json"]),
        "previous_hmac": ligne_de_la_cloture["previous_hmac"],
    }
    message = json.dumps(
        donnees, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hmac.new(
        cle.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


class ReleveDesLieuxVerifies:
    """
    Remplace la vérification de la chaîne des ventes par un relevé : chaque appel
    note le schéma du lieu courant, et ne trouve aucune anomalie.
    / Replaces the sales chain check by a record of the current venue's schema.
    """

    def __init__(self):
        self.lieux_verifies = []

    def noter_le_lieu_courant(self, cle, *arguments, **options):
        self.lieux_verifies.append(connection.schema_name)
        return []


# ---------------------------------------------------------------------- #
#  Tests sans base : retraits                                             #
#  / Tests without database: removals                                     #
# ---------------------------------------------------------------------- #


def test_les_taches_de_cloture_de_la_caisse_jamais_planifiees_n_existent_plus():
    """
    Les tâches de clôture de la caisse, jamais planifiées, sont retirées : ni dans
    `laboutik/tasks.py`, ni dans le registre de Celery, ni dans le planning
    (`TiBillet/celery.py`), ni chez un appelant de production. Les clôtures
    automatiques passent par `comptabilite/tasks.py`.
    / The never-scheduled register closure tasks are gone everywhere.
    """
    import laboutik.tasks
    from TiBillet.celery import app

    noms_des_taches_enregistrees = list(app.tasks.keys())
    racine_du_depot = Path(settings.BASE_DIR)
    texte_du_planning = (racine_du_depot / "TiBillet" / "celery.py").read_text(
        encoding="utf-8"
    )
    fichiers_de_production = fichiers_python_de_production()

    for nom_de_la_tache in NOMS_DES_TACHES_DE_CLOTURE_RETIREES:
        assert not hasattr(laboutik.tasks, nom_de_la_tache), nom_de_la_tache
        assert (
            f"laboutik.tasks.{nom_de_la_tache}" not in noms_des_taches_enregistrees
        ), nom_de_la_tache
        assert nom_de_la_tache not in texte_du_planning, nom_de_la_tache

    fichiers_qui_citent_une_tache_retiree = []
    for chemin_relatif in fichiers_de_production:
        source_du_fichier = (racine_du_depot / chemin_relatif).read_text(
            encoding="utf-8", errors="ignore"
        )
        for nom_de_la_tache in NOMS_DES_TACHES_DE_CLOTURE_RETIREES:
            if re.search(rf"\b{nom_de_la_tache}\b", source_du_fichier):
                fichiers_qui_citent_une_tache_retiree.append(
                    f"{chemin_relatif} : {nom_de_la_tache}"
                )
    assert fichiers_qui_citent_une_tache_retiree == [], (
        fichiers_qui_citent_une_tache_retiree
    )


def test_aucun_code_de_production_n_ecrit_l_ancienne_cloture():
    """
    Plus aucun code de production n'écrit une `laboutik.ClotureCaisse` : le bouton
    « Clôturer », les tâches et les données de démonstration écrivent la clôture
    unique (`comptabilite.ClotureCaisse`). Seuls l'admin de l'ancienne clôture et les
    migrations la citent encore.
    / No production code writes an old closure anymore (except its admin and the
    migrations).
    """
    racine_du_depot = Path(settings.BASE_DIR)
    fichiers_de_production = fichiers_python_de_production()
    ecritures_trouvees = []

    for chemin_relatif in fichiers_de_production:
        if chemin_relatif == FICHIER_DE_L_ADMIN_DE_L_ANCIENNE_CLOTURE:
            continue
        source_du_fichier = (racine_du_depot / chemin_relatif).read_text(
            encoding="utf-8", errors="ignore"
        )
        noms_locaux = noms_locaux_de_l_ancienne_cloture(source_du_fichier)
        for nom_local in noms_locaux:
            numeros_de_ligne = ecritures_de_l_ancienne_cloture(
                source_du_fichier, nom_local
            )
            for numero_de_ligne in numeros_de_ligne:
                ecritures_trouvees.append(f"{chemin_relatif}:{numero_de_ligne}")

    assert ecritures_trouvees == [], ecritures_trouvees


# Une référence de code à l'ancienne clôture par son nom d'application : la chaîne
# 'laboutik.ClotureCaisse' entre guillemets (une ForeignKey, un `get_model`).
# / A code reference to the old closure by app label.
REFERENCE_A_L_ANCIENNE_CLOTURE_PAR_SON_NOM = re.compile(
    r"""["']laboutik\.ClotureCaisse["']"""
)

# La définition d'une classe `ClotureCaisse` : dans l'app `laboutik`, c'est l'ancienne
# clôture (celle de `comptabilite` est la clôture unique).
# / A ClotureCaisse class definition: in the laboutik app, it is the old closure.
DEFINITION_D_UNE_CLASSE_CLOTURE_CAISSE = re.compile(
    r"^class ClotureCaisse\(", re.MULTILINE
)


def fichier_qui_cite_l_ancienne_cloture(chemin_relatif, source_du_fichier):
    """
    Dit si un fichier de production cite l'ancienne clôture (`laboutik.ClotureCaisse`)
    dans son code : il l'importe des modèles de la caisse, ou la référence par son nom
    d'application (`'laboutik.ClotureCaisse'`), ou il la définit (une classe
    `ClotureCaisse` dans l'app `laboutik`). Un commentaire ou une docstring qui la
    nomme sans guillemets ne compte pas.
    / Tells whether a production file cites the old closure in its code.
    """
    if noms_locaux_de_l_ancienne_cloture(source_du_fichier):
        return True
    if REFERENCE_A_L_ANCIENNE_CLOTURE_PAR_SON_NOM.search(source_du_fichier):
        return True
    fichier_de_l_app_de_la_caisse = chemin_relatif.parts[0] == "laboutik"
    definit_une_cloture = (
        DEFINITION_D_UNE_CLASSE_CLOTURE_CAISSE.search(source_du_fichier) is not None
    )
    return fichier_de_l_app_de_la_caisse and definit_une_cloture


def test_seuls_les_fichiers_de_la_liste_blanche_citent_l_ancienne_cloture():
    """
    Liste blanche : seuls les fichiers de `FICHIERS_QUI_PEUVENT_CITER_L_ANCIENNE_CLOTURE`
    citent l'ancienne clôture dans leur code (import, référence par son nom, ou
    définition). Un nouveau fichier qui la cite — même pour la lire — fait échouer le
    test : la clôture du lieu est `comptabilite.ClotureCaisse`.
    / Whitelist: only the listed files cite the old closure; a new one fails.
    """
    racine_du_depot = Path(settings.BASE_DIR)
    fichiers_de_production = fichiers_python_de_production()
    fichiers_hors_liste_blanche = []

    for chemin_relatif in fichiers_de_production:
        source_du_fichier = (racine_du_depot / chemin_relatif).read_text(
            encoding="utf-8", errors="ignore"
        )
        cite_l_ancienne_cloture = fichier_qui_cite_l_ancienne_cloture(
            chemin_relatif, source_du_fichier
        )
        if not cite_l_ancienne_cloture:
            continue
        if chemin_relatif not in FICHIERS_QUI_PEUVENT_CITER_L_ANCIENNE_CLOTURE:
            fichiers_hors_liste_blanche.append(str(chemin_relatif))

    assert fichiers_hors_liste_blanche == [], fichiers_hors_liste_blanche


# ---------------------------------------------------------------------- #
#  Tests sur un lieu dédié                                                #
#  / Tests on a dedicated venue                                           #
# ---------------------------------------------------------------------- #


class TestArchiveLneDesVentes(FastTenantTestCase):
    """
    L'archive fiscale, la vérification d'intégrité et le bouton « Export fiscal », sur
    un lieu qui ne contient que les ventes et les clôtures du test.
    / The fiscal archive, the integrity check and the "Fiscal export" button.
    """

    @classmethod
    def get_test_schema_name(cls):
        return "test_archive_lne_ventes"

    @classmethod
    def get_test_tenant_domain(cls):
        return "test-archive-lne-ventes.tibillet.localhost"

    @classmethod
    def setup_tenant(cls, tenant):
        """`Client.name` est unique et obligatoire. / Client.name is unique."""
        tenant.name = "Test archive LNE ventes"

    def setUp(self):
        """
        Le lieu de test : son singleton de caisse, sa configuration (caisse active,
        Paris, aucun e-mail de rapport), un point de vente, un jus à 3,50 € et un
        administrateur connecté.
        / The test venue: register singleton, configuration, a point of sale, a juice
        and a logged-in admin.
        """
        # Le rollback du test précédent a rendu le `search_path` au public.
        # / The previous test's rollback returned the search_path to public.
        connection.set_tenant(self.tenant)

        # Le singleton de la caisse doit exister en base (tests/PIEGES.md 9.86) : il
        # porte la clé des empreintes des ventes et des clôtures.
        # / The register singleton must exist in the database (fingerprint key).
        LaboutikConfiguration.get_solo().save()

        # Les routes de la caisse (export fiscal) sont gardées par `module_caisse`, qui
        # exige `module_monnaie_locale`. Aucun e-mail de rapport : la J n'envoie rien.
        # Toutes les valeurs sont écrites ici : le cache garde celles du test précédent.
        # / Register routes need module_caisse. No report e-mail. Every value written.
        configuration = Configuration.get_solo()
        configuration.module_monnaie_locale = True
        configuration.module_caisse = True
        configuration.fuseau_horaire = "Europe/Paris"
        configuration.rapport_emails = ""
        configuration.save()

        self.point_de_vente = PointDeVente.objects.create(
            name="Bar archive LNE",
            comportement=PointDeVente.DIRECT,
            service_direct=True,
            accepte_especes=True,
            accepte_carte_bancaire=True,
        )

        self.tarif_du_jus = creer_tarif_vendu(
            nom="Jus",
            prix_en_euros="3.50",
            taux_tva="20.00",
        )

        # L'administrateur vit dans le schéma public (SHARED_APPS) ; il est créé dans
        # la transaction du test, annulée à la fin.
        # / The admin lives in the public schema; created inside the rolled-back test.
        self.administrateur_du_lieu, _utilisateur_cree = (
            TibilletUser.objects.get_or_create(
                email="admin-test-archive-lne@tibillet.localhost",
                defaults={
                    "username": "admin-test-archive-lne@tibillet.localhost",
                    "is_staff": True,
                    "is_active": True,
                },
            )
        )
        self.administrateur_du_lieu.client_admin.add(self.tenant)
        self.navigateur = TenantClient(self.tenant, HTTP_ACCEPT_LANGUAGE="fr")
        self.navigateur.force_login(self.administrateur_du_lieu)

    # ------------------------------------------------------------------
    # Outils du test
    # / Test helpers
    # ------------------------------------------------------------------

    def _vendre_trois_jus_en_monnaie_locale_et_carte_bancaire(self):
        """
        Trois jus à 3,50 € (10,50 €), payés 5,00 € en monnaie locale et 5,50 € par
        carte bancaire : deux « parts » de l'article, chacune avec son argent réel
        (tronc §5). Rend la vente réglée.
        / Three juices paid 5.00 € local currency + 5.50 € card: two parts.
        """
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.428571"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 500,
                    "payment_method": PaymentMethod.LOCAL_EURO,
                    "status": LigneArticle.VALID,
                },
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1.571429"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "total_catalogue_impose": 550,
                    "payment_method": PaymentMethod.CC,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[
                {"moyen": PaymentMethod.LOCAL_EURO, "montant": 500},
                {"moyen": PaymentMethod.CC, "montant": 550},
            ],
        )
        verifier_egalites(vente)
        return vente

    def _vendre_un_jus_en_especes(self, origine=SaleOrigin.LABOUTIK):
        """
        Un jus à 3,50 € payé en espèces (règlement espèces de 350). Rend la vente.
        / One 3.50 € juice paid in cash. Returns the sale.
        """
        vente = fabriquer_vente_encaissee(
            origine=origine,
            point_de_vente=self.point_de_vente,
            articles=[
                {
                    "pricesold": self.tarif_du_jus,
                    "quantite": Decimal("1"),
                    "prix_unitaire": 350,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.CASH,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )
        verifier_egalites(vente)
        return vente

    def _cloturer_la_journee(self):
        """
        La J unique du lieu, créée par la vraie tâche de clôture. Rend la J.
        / The venue's single J, created by the real closure task.
        """
        uuid_de_la_j = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_JOURNALIER,
        )
        return ClotureCaisse.objects.get(uuid=uuid_de_la_j)

    def _fichiers_de_l_archive(self):
        """
        Les fichiers de l'archive fiscale du lieu, sans borne de dates.
        / The venue's fiscal archive files, with no date bounds.
        """
        return generer_fichiers_archive(schema=self.tenant.schema_name)

    # ------------------------------------------------------------------
    # L'archive fiscale
    # / The fiscal archive
    # ------------------------------------------------------------------

    def test_archive_lne_fichiers_des_ventes_et_pas_de_corrections(self):
        """
        L'archive porte les quatre fichiers des ventes et des clôtures, chacun avec ses
        colonnes ; l'ancien `corrections.csv` n'existe plus, ni dans les fichiers ni
        dans les données JSON ni dans les compteurs.
        / The archive carries the four files with their columns; no corrections.csv.
        """
        self._vendre_un_jus_en_especes()

        fichiers = self._fichiers_de_l_archive()

        for nom_du_fichier in FICHIERS_DES_VENTES_ET_DES_CLOTURES:
            assert nom_du_fichier in fichiers, sorted(fichiers.keys())
            colonnes_du_fichier = colonnes_du_csv(fichiers[nom_du_fichier])
            colonnes_attendues = COLONNES_ATTENDUES_PAR_FICHIER[nom_du_fichier]
            assert colonnes_du_fichier == colonnes_attendues, (
                nom_du_fichier,
                colonnes_du_fichier,
            )
        assert FICHIER_DES_CORRECTIONS_RETIRE not in fichiers, sorted(fichiers.keys())

        donnees_de_l_archive = json.loads(fichiers["donnees.json"].decode("utf-8"))
        assert "corrections" not in donnees_de_l_archive, sorted(
            donnees_de_l_archive.keys()
        )
        metadonnees_de_l_archive = json.loads(fichiers["meta.json"].decode("utf-8"))
        compteurs = metadonnees_de_l_archive["compteurs"]
        assert "corrections" not in compteurs, compteurs
        # Une vente, un article, un règlement, aucune clôture.
        # / One sale, one item, one payment, no closure.
        assert compteurs["ventes"] == 1, compteurs
        assert compteurs["articles"] == 1, compteurs
        assert compteurs["reglements"] == 1, compteurs
        assert compteurs["clotures"] == 0, compteurs

    def test_archive_lne_tva_stockee_175(self):
        """
        Trois jus payés 5,00 € en monnaie locale et 5,50 € par carte bancaire.
        L'archive exporte la TVA STOCKÉE : 83 + 92 = 175 sur les articles, et 175 sur
        la vente (une TVA recalculée depuis `amount × qty` donnerait 82 + 92 = 174).
        / The archive exports the STORED VAT: 83 + 92 = 175 (a recomputed one: 174).
        """
        vente = self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()

        fichiers = self._fichiers_de_l_archive()

        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        ligne_de_la_vente = lignes_dont_la_colonne_vaut(
            lignes_des_ventes, "uuid", str(vente.uuid)
        )
        assert len(ligne_de_la_vente) == 1, lignes_des_ventes
        assert ligne_de_la_vente[0]["total_ttc"] == "1050"
        assert ligne_de_la_vente[0]["total_ht"] == "875"
        assert ligne_de_la_vente[0]["total_tva"] == "175"

        lignes_des_articles = lignes_du_csv(fichiers["articles.csv"])
        articles_de_la_vente = lignes_dont_la_colonne_vaut(
            lignes_des_articles, "vente_uuid", str(vente.uuid)
        )
        montants_des_parts = []
        for article in articles_de_la_vente:
            montants_des_parts.append(
                (article["total_ttc"], article["total_ht"], article["total_tva"])
            )
        assert sorted(montants_des_parts) == [
            ("500", "417", "83"),
            ("550", "458", "92"),
        ], montants_des_parts

        somme_des_tva_des_articles = 0
        for article in articles_de_la_vente:
            somme_des_tva_des_articles += int(article["total_tva"])
        assert somme_des_tva_des_articles == 175

        # Les valeurs exportées sont celles stockées sur les articles, en base.
        # / The exported values are the ones stored on the items.
        for article in articles_de_la_vente:
            article_en_base = LigneArticle.objects.get(uuid=article["uuid"])
            assert article["total_ht"] == str(article_en_base.total_ht)
            assert article["total_tva"] == str(article_en_base.total_tva)

    def test_archive_lne_contient_tireuse_et_en_ligne(self):
        """
        Une vente de la tireuse (4,00 € en monnaie locale) et une vente en ligne
        (15,00 € par Stripe) sont dans l'archive, avec leur origine, leur article et
        leur règlement : l'archive porte les ventes de toutes les origines.
        / A tap sale and an online sale are archived, with origin, item and payment.
        """
        vente_de_la_tireuse = fabriquer_vente_encaissee(
            origine=SaleOrigin.TIREUSE,
            articles=[
                {
                    "pricesold": creer_tarif_vendu(nom="Biere pression"),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 400,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.LOCAL_EURO,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.LOCAL_EURO, "montant": 400}],
        )
        vente_en_ligne = fabriquer_vente_encaissee(
            origine=SaleOrigin.LESPASS,
            articles=[
                {
                    "pricesold": creer_tarif_vendu(nom="Billet", prix_en_euros="15.00"),
                    "quantite": Decimal("1"),
                    "prix_unitaire": 1500,
                    "taux_tva": Decimal("20"),
                    "payment_method": PaymentMethod.STRIPE_NOFED,
                    "status": LigneArticle.VALID,
                },
            ],
            reglements=[{"moyen": PaymentMethod.STRIPE_NOFED, "montant": 1500}],
        )

        fichiers = self._fichiers_de_l_archive()

        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        lignes_des_articles = lignes_du_csv(fichiers["articles.csv"])
        lignes_des_reglements = lignes_du_csv(fichiers["reglements.csv"])
        ventes_et_origines_attendues = [
            (vente_de_la_tireuse, SaleOrigin.TIREUSE, PaymentMethod.LOCAL_EURO, "400"),
            (vente_en_ligne, SaleOrigin.LESPASS, PaymentMethod.STRIPE_NOFED, "1500"),
        ]
        for vente, origine, moyen, montant in ventes_et_origines_attendues:
            ligne_de_la_vente = lignes_dont_la_colonne_vaut(
                lignes_des_ventes, "uuid", str(vente.uuid)
            )
            assert len(ligne_de_la_vente) == 1, (origine, lignes_des_ventes)
            assert ligne_de_la_vente[0]["origine"] == origine

            articles_de_la_vente = lignes_dont_la_colonne_vaut(
                lignes_des_articles, "vente_uuid", str(vente.uuid)
            )
            assert len(articles_de_la_vente) == 1, (origine, articles_de_la_vente)
            assert articles_de_la_vente[0]["total_ttc"] == montant

            reglements_de_la_vente = lignes_dont_la_colonne_vaut(
                lignes_des_reglements, "vente_uuid", str(vente.uuid)
            )
            reglements_lus = []
            for reglement in reglements_de_la_vente:
                reglements_lus.append((reglement["moyen"], reglement["montant"]))
            assert reglements_lus == [(moyen, montant)], (origine, reglements_lus)

    def test_archive_lne_ventes_portent_leur_empreinte_chainee(self):
        """
        Deux ventes : chacune porte dans `ventes.csv` son numéro et son empreinte
        stockée ; le `previous_hmac` de la vente n° 2 est l'empreinte de la vente n° 1
        ("" pour la première).
        / Each sale carries its number and stored fingerprint; sale 2 links to sale 1.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        premiere_vente.refresh_from_db()
        deuxieme_vente.refresh_from_db()

        fichiers = self._fichiers_de_l_archive()

        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        ligne_de_la_premiere = lignes_dont_la_colonne_vaut(
            lignes_des_ventes, "uuid", str(premiere_vente.uuid)
        )[0]
        ligne_de_la_deuxieme = lignes_dont_la_colonne_vaut(
            lignes_des_ventes, "uuid", str(deuxieme_vente.uuid)
        )[0]
        assert ligne_de_la_premiere["numero"] == "1"
        assert ligne_de_la_premiere["hmac_hash"] == premiere_vente.hmac_hash
        assert ligne_de_la_premiere["previous_hmac"] == ""
        assert ligne_de_la_deuxieme["numero"] == "2"
        assert ligne_de_la_deuxieme["hmac_hash"] == deuxieme_vente.hmac_hash
        assert ligne_de_la_deuxieme["previous_hmac"] == premiere_vente.hmac_hash
        assert premiere_vente.hmac_hash != ""

    def test_archive_lne_correction_est_une_vente_correction(self):
        """
        Un jus payé en espèces (350), puis corrigé en carte bancaire : la correction
        est une vente « CORRECTION » liée à la vente d'origine, avec deux règlements
        qui s'annulent (espèces −350, carte bancaire +350). L'archive la porte dans
        `ventes.csv` et `reglements.csv`.
        / A cash juice corrected to card: a CORRECTION sale linked to the original,
        with two payments that cancel out, in ventes.csv and reglements.csv.
        """
        vente_d_origine = self._vendre_un_jus_en_especes()
        vente_de_correction = ouvrir_vente(
            origine=SaleOrigin.LABOUTIK,
            nature=Vente.Nature.CORRECTION,
            point_de_vente=self.point_de_vente,
            vente_liee=vente_d_origine,
        )
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CASH, montant=-350)
        ajouter_reglement(vente_de_correction, moyen=PaymentMethod.CC, montant=350)
        encaisser_vente(vente_de_correction)

        fichiers = self._fichiers_de_l_archive()

        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        ligne_de_la_correction = lignes_dont_la_colonne_vaut(
            lignes_des_ventes, "uuid", str(vente_de_correction.uuid)
        )
        assert len(ligne_de_la_correction) == 1, lignes_des_ventes
        assert ligne_de_la_correction[0]["nature"] == Vente.Nature.CORRECTION
        assert ligne_de_la_correction[0]["vente_liee_uuid"] == str(vente_d_origine.uuid)

        lignes_des_reglements = lignes_du_csv(fichiers["reglements.csv"])
        reglements_de_la_correction = lignes_dont_la_colonne_vaut(
            lignes_des_reglements, "vente_uuid", str(vente_de_correction.uuid)
        )
        reglements_lus = []
        for reglement in reglements_de_la_correction:
            reglements_lus.append((reglement["moyen"], reglement["montant"]))
        assert sorted(reglements_lus) == [
            (PaymentMethod.CASH, "-350"),
            (PaymentMethod.CC, "350"),
        ], reglements_lus

    def test_archive_lne_clotures_uniques_jamais_l_ancienne(self):
        """
        Un jus vendu, puis la J unique du lieu. Une ancienne clôture
        (`laboutik.ClotureCaisse`) existe aussi en base : `clotures.csv` porte la J
        unique (niveau, numéro, plage de ventes, total 350, empreinte), jamais
        l'ancienne.
        / clotures.csv carries the single J, never the old closure.
        """
        self._vendre_un_jus_en_especes()
        cloture_j = self._cloturer_la_journee()
        maintenant = timezone.now()
        ancienne_cloture = AncienneClotureCaisse.objects.create(
            point_de_vente=self.point_de_vente,
            datetime_ouverture=maintenant,
            datetime_cloture=maintenant,
            niveau=AncienneClotureCaisse.JOURNALIERE,
            numero_sequentiel=1,
            total_especes=350,
            total_general=350,
            nombre_transactions=1,
        )

        fichiers = self._fichiers_de_l_archive()

        lignes_des_clotures = lignes_du_csv(fichiers["clotures.csv"])
        uuids_des_clotures = []
        for ligne in lignes_des_clotures:
            uuids_des_clotures.append(ligne["uuid"])
        assert uuids_des_clotures == [str(cloture_j.uuid)], uuids_des_clotures
        assert str(ancienne_cloture.uuid) not in uuids_des_clotures

        ligne_de_la_j = lignes_des_clotures[0]
        assert ligne_de_la_j["niveau"] == ClotureCaisse.NIVEAU_JOURNALIER
        assert ligne_de_la_j["numero_sequentiel"] == "1"
        assert ligne_de_la_j["numero_premiere_vente"] == "1"
        assert ligne_de_la_j["numero_derniere_vente"] == "1"
        assert ligne_de_la_j["total_general"] == "350"
        assert ligne_de_la_j["hmac_hash"] == cloture_j.hmac_hash
        assert ligne_de_la_j["previous_hmac"] == ""
        assert cloture_j.hmac_hash != ""

    def test_readme_fiscal_decrit_les_fichiers_des_ventes(self):
        """
        Le README de l'archive décrit les quatre fichiers des ventes et des clôtures,
        et ne cite pas `corrections.csv` (ce fichier n'existe pas).
        / The archive README describes the four files and does not cite
        corrections.csv.
        """
        texte_du_readme = generer_readme_fiscal(self.tenant.schema_name).decode("utf-8")

        for nom_du_fichier in FICHIERS_DES_VENTES_ET_DES_CLOTURES:
            assert nom_du_fichier in texte_du_readme, nom_du_fichier
        assert FICHIER_DES_CORRECTIONS_RETIRE not in texte_du_readme

    # ------------------------------------------------------------------
    # La vérification d'intégrité
    # / The integrity check
    # ------------------------------------------------------------------

    def test_verify_integrity_chaines_saines_sort_avec_zero(self):
        """
        Deux ventes et leur J, rien d'altéré : `verify_integrity` ne signale rien et
        sort avec le code 0.
        / Sound chains: verify_integrity reports nothing and exits with 0.
        """
        self._vendre_un_jus_en_especes()
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._cloturer_la_journee()

        texte_de_la_sortie, code_de_sortie = lancer_la_commande(
            "verify_integrity", f"--schema={self.tenant.schema_name}"
        )

        assert code_de_sortie == 0, texte_de_la_sortie
        assert "Empreinte fausse" not in texte_de_la_sortie, texte_de_la_sortie

    def test_verify_integrity_detecte_article_modifie(self):
        """
        Un centime passe du HT à la TVA d'un article après l'encaissement (`update()`,
        une écriture à la main) : HT 292 → 291, TVA 58 → 59. HT + TVA reste égal au
        TTC (350), la contrainte de la base l'accepte ; seule l'empreinte le voit.
        `verify_integrity` signale l'empreinte fausse de la vente n° 1 et sort avec un
        code différent de 0.
        Valeurs : 350 / 1,2 = 291,67 → HT 292, TVA 58.
        / One cent moves from HT to VAT on an item: only the fingerprint sees it;
        verify_integrity reports it and exits with ≠ 0.
        """
        vente = self._vendre_un_jus_en_especes()
        article_de_la_vente = LigneArticle.objects.get(vente=vente)
        assert (article_de_la_vente.total_ht, article_de_la_vente.total_tva) == (292, 58)
        LigneArticle.objects.filter(pk=article_de_la_vente.pk).update(
            total_ht=291, total_tva=59
        )

        texte_de_la_sortie, code_de_sortie = lancer_la_commande(
            "verify_integrity", f"--schema={self.tenant.schema_name}"
        )

        assert code_de_sortie != 0, texte_de_la_sortie
        assert "Empreinte fausse : la vente n° 1" in texte_de_la_sortie, (
            texte_de_la_sortie
        )

    def test_verify_integrity_detecte_une_cloture_alteree(self):
        """
        Le rapport stocké de la J est modifié en base (`update()`) : `verify_integrity`
        lit aussi la chaîne des clôtures, signale l'empreinte fausse de la clôture n° 1
        et sort avec un code différent de 0.
        / The J's stored report is tampered with: verify_integrity also reads the
        closures chain and exits with ≠ 0.
        """
        self._vendre_un_jus_en_especes()
        cloture_j = self._cloturer_la_journee()
        rapport_altere = dict(cloture_j.rapport_json)
        rapport_altere["chiffre_affaires"] = dict(rapport_altere["chiffre_affaires"])
        rapport_altere["chiffre_affaires"]["total_ttc_en_centimes"] = 1
        ClotureCaisse.objects.filter(pk=cloture_j.pk).update(rapport_json=rapport_altere)

        texte_de_la_sortie, code_de_sortie = lancer_la_commande(
            "verify_integrity", f"--schema={self.tenant.schema_name}"
        )

        assert code_de_sortie != 0, texte_de_la_sortie
        assert "Empreinte fausse : la clôture n° 1" in texte_de_la_sortie, (
            texte_de_la_sortie
        )

    # ------------------------------------------------------------------
    # Le bouton « Export fiscal » de la liste des clôtures uniques
    # / The "Fiscal export" button of the single closures list
    # ------------------------------------------------------------------

    def test_liste_des_clotures_uniques_porte_le_bouton_export_fiscal(self):
        """
        La liste des clôtures uniques de l'admin porte, dans son bandeau, le bouton
        « Export fiscal » (`data-testid="btn-export-fiscal"`). Le bouton charge le
        formulaire de l'export (`data-testid="export-fiscal-form"`).
        / The single closures list carries the "Fiscal export" button, which loads
        the export form.
        """
        reponse_de_la_liste = self.navigateur.get(
            reverse("staff_admin:comptabilite_cloturecaisse_changelist")
        )

        assert reponse_de_la_liste.status_code == 200
        boutons_export_fiscal = attributs_des_elements(
            reponse_de_la_liste.content.decode(), "btn-export-fiscal"
        )
        assert len(boutons_export_fiscal) == 1, boutons_export_fiscal
        adresse_du_formulaire = boutons_export_fiscal[0].get("hx-get")
        assert adresse_du_formulaire, boutons_export_fiscal[0]

        reponse_du_formulaire = self.navigateur.get(
            adresse_du_formulaire, HTTP_HX_REQUEST="true"
        )

        assert reponse_du_formulaire.status_code == 200
        formulaires = attributs_des_elements(
            reponse_du_formulaire.content.decode(), "export-fiscal-form"
        )
        assert len(formulaires) == 1, reponse_du_formulaire.content.decode()[:400]

    def _ouvrir_le_formulaire_de_l_export_fiscal_sans_module_caisse(self):
        """
        Le lieu n'a PAS le module caisse (une billetterie en ligne seule). L'admin
        ouvre la liste des clôtures uniques et clique « Export fiscal » : le bouton
        existe, et son adresse est une adresse de l'ADMIN (`/admin/…`), pas une route
        de la caisse. Rend l'adresse de l'export.
        / The venue has NO register module: the button exists and points to an ADMIN
        address. Returns the export address.
        """
        configuration = Configuration.get_solo()
        configuration.module_caisse = False
        configuration.save()

        reponse_de_la_liste = self.navigateur.get(
            reverse("staff_admin:comptabilite_cloturecaisse_changelist")
        )

        assert reponse_de_la_liste.status_code == 200
        boutons_export_fiscal = attributs_des_elements(
            reponse_de_la_liste.content.decode(), "btn-export-fiscal"
        )
        assert len(boutons_export_fiscal) == 1, boutons_export_fiscal
        adresse_de_l_export = boutons_export_fiscal[0].get("hx-get")
        assert adresse_de_l_export.startswith("/admin/"), adresse_de_l_export
        return adresse_de_l_export

    def test_bouton_export_fiscal_present_sans_module_caisse(self):
        """
        L'archive fiscale couvre toutes les origines (en ligne, admin, caisse) : un
        lieu SANS module caisse a lui aussi le bouton « Export fiscal ». Le bouton
        charge le formulaire de l'export (`data-testid="export-fiscal-form"`), servi
        par l'admin de la comptabilité.
        / The archive covers every origin: a venue WITHOUT the register module also
        gets the button, which loads the export form from the accounting admin.
        """
        adresse_de_l_export = (
            self._ouvrir_le_formulaire_de_l_export_fiscal_sans_module_caisse()
        )

        reponse_du_formulaire = self.navigateur.get(
            adresse_de_l_export, HTTP_HX_REQUEST="true"
        )

        assert reponse_du_formulaire.status_code == 200
        formulaires = attributs_des_elements(
            reponse_du_formulaire.content.decode(), "export-fiscal-form"
        )
        assert len(formulaires) == 1, reponse_du_formulaire.content.decode()[:400]

    def test_export_fiscal_sans_module_caisse_rend_l_archive(self):
        """
        Sans module caisse, l'admin envoie le formulaire de l'export (date de début
        posée) : la réponse est l'archive ZIP, en téléchargement.
        / Without the register module, posting the export form returns the ZIP archive.
        """
        self._vendre_un_jus_en_especes()
        adresse_de_l_export = (
            self._ouvrir_le_formulaire_de_l_export_fiscal_sans_module_caisse()
        )

        # Début = il y a 30 jours, dans le fuseau du lieu : la période reste sous le
        # plafond de 365 jours quelle que soit la date du jour.
        # / Start = 30 days ago in the venue's time zone: stays under the 365-day cap.
        fuseau_du_lieu = Configuration.get_solo().get_tzinfo()
        aujourd_hui_au_lieu = timezone.now().astimezone(fuseau_du_lieu).date()
        debut_de_l_export = aujourd_hui_au_lieu - timedelta(days=30)

        reponse_de_l_export = self.navigateur.post(
            adresse_de_l_export, {"debut": debut_de_l_export.isoformat()}
        )

        assert reponse_de_l_export.status_code == 200, (
            reponse_de_l_export.content.decode(errors="replace")[:400]
        )
        assert reponse_de_l_export["Content-Type"] == "application/zip"
        assert "attachment" in reponse_de_l_export["Content-Disposition"]

    # ------------------------------------------------------------------
    # La route d'export fiscal : la période
    # / The fiscal export route: the period
    # ------------------------------------------------------------------

    def test_export_fiscal_periode_plafonnee_a_365_jours(self):
        """
        La route d'export fiscal plafonne la période comme la commande
        `archiver_donnees` : du 01/01/2025 au 02/01/2026 (366 jours) → refus 400 ; une
        fin avant le début → refus 400 ; du 01/01/2025 au 31/12/2025 (364 jours) →
        l'archive ZIP.
        / The export route caps the period at 365 days, like the command.
        """
        adresse_de_l_export = reverse("laboutik-caisse-export_fiscal")

        reponse_trop_longue = self.navigateur.post(
            adresse_de_l_export, data={"debut": "2025-01-01", "fin": "2026-01-02"}
        )
        reponse_a_l_envers = self.navigateur.post(
            adresse_de_l_export, data={"debut": "2025-03-01", "fin": "2025-02-01"}
        )
        reponse_d_une_annee = self.navigateur.post(
            adresse_de_l_export, data={"debut": "2025-01-01", "fin": "2025-12-31"}
        )

        assert reponse_trop_longue.status_code == 400
        assert "365 jours" in reponse_trop_longue.content.decode()
        assert reponse_a_l_envers.status_code == 400
        assert reponse_d_une_annee.status_code == 200
        assert reponse_d_une_annee["Content-Type"] == "application/zip"

    def test_export_fiscal_fin_sans_debut_refusee(self):
        """
        La date de début de l'export fiscal est obligatoire, comme pour la commande
        `archiver_donnees` : une fin sans début → refus 400, avec un message clair,
        et aucune archive.
        / The start date is required: an end without a start → 400 and a clear
        message, no archive.
        """
        adresse_de_l_export = reverse("laboutik-caisse-export_fiscal")

        reponse_sans_debut = self.navigateur.post(
            adresse_de_l_export, data={"fin": "2025-02-01"}
        )

        assert reponse_sans_debut.status_code == 400
        assert reponse_sans_debut["Content-Type"] != "application/zip"
        assert "La date de début est obligatoire." in (
            reponse_sans_debut.content.decode()
        )

    # ------------------------------------------------------------------
    # Le contenu de l'archive : rapports, liens, empreintes, bornes
    # / Archive content: reports, links, fingerprints, bounds
    # ------------------------------------------------------------------

    def test_archive_lne_porte_le_rapport_de_chaque_cloture(self):
        """
        Trois jus payés 5,00 € en monnaie locale et 5,50 € par CB, puis la J. Le
        rapport complet de la J est dans l'archive : dans `clotures.csv` (colonne
        `rapport_json`, JSON canonique : clés triées, sans espace) et dans
        `donnees.json` (l'objet entier). La ventilation se retrouve : par moyen
        (monnaie locale 500, CB 550) et par taux (20,00 % : TTC 1050).
        / The J's full report is archived (canonical JSON column + whole object):
        by method and by rate.
        """
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        cloture_j = self._cloturer_la_journee()

        fichiers = self._fichiers_de_l_archive()

        ligne_de_la_j = lignes_du_csv(fichiers["clotures.csv"])[0]
        texte_attendu = json.dumps(
            cloture_j.rapport_json,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        assert ligne_de_la_j["rapport_json"] == texte_attendu
        rapport_archive = json.loads(ligne_de_la_j["rapport_json"])
        par_moyen = rapport_archive["chiffre_affaires"]["par_moyen"]
        assert par_moyen[PaymentMethod.LOCAL_EURO]["total_en_centimes"] == 500
        assert par_moyen[PaymentMethod.CC]["total_en_centimes"] == 550
        par_taux = rapport_archive["chiffre_affaires"]["par_taux"]
        assert par_taux["20.00"]["total_ttc_en_centimes"] == 1050

        donnees_de_l_archive = json.loads(fichiers["donnees.json"].decode("utf-8"))
        assert donnees_de_l_archive["clotures"][0]["rapport_json"] == (
            cloture_j.rapport_json
        )

    def test_archive_lne_article_porte_l_uuid_de_transaction(self):
        """
        Un jus vendu avec un identifiant de paiement (`uuid_transaction`) : l'article
        de l'archive porte cet identifiant, qui relie un ticket imprimé
        (`impressions.csv`) à sa vente.
        / The archived item carries its payment id, linking a printed ticket to it.
        """
        identifiant_du_paiement = uuid.uuid4()
        vente = fabriquer_vente_encaissee(
            origine=SaleOrigin.LABOUTIK,
            point_de_vente=self.point_de_vente,
            articles=[{
                "pricesold": self.tarif_du_jus,
                "quantite": Decimal("1"),
                "prix_unitaire": 350,
                "taux_tva": Decimal("20"),
                "uuid_transaction": identifiant_du_paiement,
            }],
            reglements=[{"moyen": PaymentMethod.CASH, "montant": 350}],
        )

        fichiers = self._fichiers_de_l_archive()

        articles_de_la_vente = lignes_dont_la_colonne_vaut(
            lignes_du_csv(fichiers["articles.csv"]), "vente_uuid", str(vente.uuid)
        )
        assert len(articles_de_la_vente) == 1
        assert articles_de_la_vente[0]["uuid_transaction"] == str(
            identifiant_du_paiement
        )

    def test_archive_lne_empreinte_recalculee_depuis_les_fichiers(self):
        """
        L'empreinte de chaque vente se recalcule à partir des seuls fichiers de
        l'archive (`ventes.csv`, `articles.csv`, `reglements.csv`) et de la clé du
        lieu, avec le message décrit dans le README : un contrôleur n'a pas besoin de
        la base. Deux ventes : les trois jus en deux parts (monnaie locale + CB, au
        point de vente), puis un jus en espèces.
        / Each sale's fingerprint is recomputed from the archive files and the key.
        """
        self._vendre_trois_jus_en_monnaie_locale_et_carte_bancaire()
        self._vendre_un_jus_en_especes()
        cle_du_lieu = LaboutikConfiguration.get_solo().get_hmac_key()

        fichiers = self._fichiers_de_l_archive()

        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        lignes_des_articles = lignes_du_csv(fichiers["articles.csv"])
        lignes_des_reglements = lignes_du_csv(fichiers["reglements.csv"])
        assert len(lignes_des_ventes) == 2
        for ligne_de_la_vente in lignes_des_ventes:
            articles_de_la_vente = lignes_dont_la_colonne_vaut(
                lignes_des_articles, "vente_uuid", ligne_de_la_vente["uuid"]
            )
            reglements_de_la_vente = lignes_dont_la_colonne_vaut(
                lignes_des_reglements, "vente_uuid", ligne_de_la_vente["uuid"]
            )
            empreinte_recalculee = empreinte_recalculee_depuis_l_archive(
                ligne_de_la_vente,
                articles_de_la_vente,
                reglements_de_la_vente,
                cle_du_lieu,
            )
            assert empreinte_recalculee == ligne_de_la_vente["hmac_hash"], (
                ligne_de_la_vente["numero"]
            )

    def test_archive_lne_empreinte_d_une_cloture_recalculee_depuis_les_fichiers(self):
        """
        L'empreinte de chaque clôture se recalcule à partir de sa seule ligne de
        `clotures.csv` et de la clé du lieu, avec le message décrit dans le README :
        un contrôleur n'a pas besoin de la base. Deux J chaînées : un jus en espèces
        puis la J n° 1, un autre jus puis la J n° 2. Chaque J porte l'empreinte de sa
        dernière vente, celle de `ventes.csv`.
        / Each closure's fingerprint is recomputed from its clotures.csv row and the
        key; each J carries its last sale's fingerprint.
        """
        premiere_vente = self._vendre_un_jus_en_especes()
        self._cloturer_la_journee()
        deuxieme_vente = self._vendre_un_jus_en_especes()
        self._cloturer_la_journee()
        cle_du_lieu = LaboutikConfiguration.get_solo().get_hmac_key()

        fichiers = self._fichiers_de_l_archive()

        lignes_des_clotures = lignes_du_csv(fichiers["clotures.csv"])
        assert len(lignes_des_clotures) == 2
        lignes_des_ventes = lignes_du_csv(fichiers["ventes.csv"])
        empreinte_par_uuid_de_vente = {}
        for ligne_de_la_vente in lignes_des_ventes:
            empreinte_par_uuid_de_vente[ligne_de_la_vente["uuid"]] = (
                ligne_de_la_vente["hmac_hash"]
            )
        assert lignes_des_clotures[0]["empreinte_de_la_derniere_vente"] == (
            empreinte_par_uuid_de_vente[str(premiere_vente.uuid)]
        )
        assert lignes_des_clotures[1]["empreinte_de_la_derniere_vente"] == (
            empreinte_par_uuid_de_vente[str(deuxieme_vente.uuid)]
        )
        assert lignes_des_clotures[1]["previous_hmac"] == (
            lignes_des_clotures[0]["hmac_hash"]
        )
        for ligne_de_la_cloture in lignes_des_clotures:
            empreinte_recalculee = empreinte_de_la_cloture_recalculee_depuis_l_archive(
                ligne_de_la_cloture, cle_du_lieu
            )
            assert empreinte_recalculee == ligne_de_la_cloture["hmac_hash"], (
                ligne_de_la_cloture["numero_sequentiel"]
            )

    def test_archive_lne_m_et_a_de_fin_d_annee_dans_l_archive_de_leur_annee(self):
        """
        Le lieu est à Paris. Un jus en espèces le 15/12/2025 à 20:00 (heure de Paris),
        puis la M de décembre 2025 et l'A de 2025, qui finissent toutes deux le
        01/01/2026 à 00:00 (heure de Paris), borne exclusive de leurs ventes.
        - L'archive du 01/01/2025 au 31/12/2025 finit le 01/01/2026 à 00:00 (fin
          exclusive pour les ventes) : elle porte la vente, la M et l'A.
        - L'archive du 01/01/2026 au 31/12/2026 commence à cet instant : elle ne
          porte ni la vente, ni la M, ni l'A.
        / The December M and the year's A end on 01/01/2026 00:00 Paris: they are in
        the 2025 archive, not in the 2026 one.
        """
        fuseau_de_paris = ZoneInfo("Europe/Paris")
        heure_de_la_vente = datetime(2025, 12, 15, 20, 0, tzinfo=fuseau_de_paris)
        with patch("django.utils.timezone.now", return_value=heure_de_la_vente):
            vente_de_decembre = self._vendre_un_jus_en_especes()
        uuid_de_la_m = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_MENSUEL,
            datetime_debut_iso="2025-12-01T00:00:00+01:00",
            datetime_fin_iso="2026-01-01T00:00:00+01:00",
        )
        uuid_de_l_a = comptabilite.tasks.generer_cloture_pour_tenant(
            schema_name=self.tenant.schema_name,
            niveau=ClotureCaisse.NIVEAU_ANNUEL,
            datetime_debut_iso="2025-01-01T00:00:00+01:00",
            datetime_fin_iso="2026-01-01T00:00:00+01:00",
        )
        assert uuid_de_la_m is not None
        assert uuid_de_l_a is not None

        fichiers_de_2025 = generer_fichiers_archive(
            schema=self.tenant.schema_name,
            debut=date(2025, 1, 1),
            fin=date(2025, 12, 31),
        )
        fichiers_de_2026 = generer_fichiers_archive(
            schema=self.tenant.schema_name,
            debut=date(2026, 1, 1),
            fin=date(2026, 12, 31),
        )

        uuids_des_clotures_de_2025 = set()
        for ligne_de_la_cloture in lignes_du_csv(fichiers_de_2025["clotures.csv"]):
            uuids_des_clotures_de_2025.add(ligne_de_la_cloture["uuid"])
        uuids_des_ventes_de_2025 = set()
        for ligne_de_la_vente in lignes_du_csv(fichiers_de_2025["ventes.csv"]):
            uuids_des_ventes_de_2025.add(ligne_de_la_vente["uuid"])
        assert uuids_des_clotures_de_2025 == {uuid_de_la_m, uuid_de_l_a}
        assert uuids_des_ventes_de_2025 == {str(vente_de_decembre.uuid)}

        assert lignes_du_csv(fichiers_de_2026["clotures.csv"]) == []
        assert lignes_du_csv(fichiers_de_2026["ventes.csv"]) == []

    def test_archive_lne_bornes_lues_dans_le_fuseau_du_lieu(self):
        """
        Le lieu est à Paris (UTC+1 en mars). Trois ventes en espèces :
        - 09/03/2026 22:59 UTC = 23:59 à Paris le 09/03 : hors de la journée du 10/03 ;
        - 10/03/2026 22:30 UTC = 23:30 à Paris le 10/03 : DANS la journée du 10/03 ;
        - 10/03/2026 23:30 UTC = 00:30 à Paris le 11/03 : hors de la journée du 10/03.
        L'archive du 10/03 au 10/03 ne porte que la deuxième vente, ni l'en-tête ni
        les articles des deux autres. Lue en UTC, la journée aurait pris la troisième.
        / Dates are read in the venue's time zone: only the 23:30 Paris sale is in.
        """
        fuseau_utc = ZoneInfo("UTC")
        heures_des_ventes = [
            datetime(2026, 3, 9, 22, 59, tzinfo=fuseau_utc),
            datetime(2026, 3, 10, 22, 30, tzinfo=fuseau_utc),
            datetime(2026, 3, 10, 23, 30, tzinfo=fuseau_utc),
        ]
        ventes = []
        for heure_de_la_vente in heures_des_ventes:
            with patch("django.utils.timezone.now", return_value=heure_de_la_vente):
                ventes.append(self._vendre_un_jus_en_especes())

        fichiers = generer_fichiers_archive(
            schema=self.tenant.schema_name,
            debut=date(2026, 3, 10),
            fin=date(2026, 3, 10),
        )

        uuids_des_ventes_archivees = []
        for ligne_de_la_vente in lignes_du_csv(fichiers["ventes.csv"]):
            uuids_des_ventes_archivees.append(ligne_de_la_vente["uuid"])
        assert uuids_des_ventes_archivees == [str(ventes[1].uuid)]
        ventes_des_articles = set()
        for ligne_de_l_article in lignes_du_csv(fichiers["articles.csv"]):
            ventes_des_articles.add(ligne_de_l_article["vente_uuid"])
        assert ventes_des_articles == {str(ventes[1].uuid)}

    def test_archive_lne_signature_verifiee_puis_alteree(self):
        """
        La signature de l'archive : générée, empaquetée en ZIP avec `hash.json`, elle
        est vérifiée (`verifier_hash_archive` → tout est valide). Un octet de
        `ventes.csv` changé, avec le même `hash.json` : la vérification échoue sur ce
        fichier et sur l'empreinte globale.
        / The archive signature verifies, then fails once one byte is changed.
        """
        self._vendre_un_jus_en_especes()
        cle_du_lieu = LaboutikConfiguration.get_solo().get_hmac_key()
        fichiers = self._fichiers_de_l_archive()
        empreintes_des_fichiers = calculer_hash_fichiers(fichiers, cle_du_lieu)

        archive_intacte = empaqueter_zip(fichiers, empreintes_des_fichiers)
        tout_est_valide, _details = verifier_hash_archive(archive_intacte, cle_du_lieu)
        assert tout_est_valide is True

        fichiers_alteres = dict(fichiers)
        fichiers_alteres["ventes.csv"] = fichiers["ventes.csv"].replace(
            b'"350"', b'"351"', 1
        )
        assert fichiers_alteres["ventes.csv"] != fichiers["ventes.csv"]
        archive_alteree = empaqueter_zip(fichiers_alteres, empreintes_des_fichiers)
        tout_est_valide, details = verifier_hash_archive(archive_alteree, cle_du_lieu)
        assert tout_est_valide is False
        fichiers_invalides = []
        for detail in details:
            if not detail["valide"]:
                fichiers_invalides.append(detail["nom"])
        assert "ventes.csv" in fichiers_invalides

    # ------------------------------------------------------------------
    # verify_integrity : les cas limites
    # / verify_integrity: edge cases
    # ------------------------------------------------------------------

    def test_verify_integrity_schema_inconnu_sort_avec_un_code_non_nul(self):
        """
        `--schema` d'un lieu qui n'existe pas : aucun lieu à vérifier, la commande
        sort avec un code différent de 0.
        / Unknown schema: no venue to verify, non-zero exit code.
        """
        texte_de_la_sortie, code_de_sortie = lancer_la_commande(
            "verify_integrity", "--schema=lieu_qui_n_existe_pas"
        )

        assert code_de_sortie != 0, texte_de_la_sortie
        assert "Aucun lieu" in texte_de_la_sortie

    def test_verify_integrity_sans_cle_avec_des_ventes_scellees(self):
        """
        Une vente scellée, puis la clé du lieu a disparu (`get_hmac_key` rend None) :
        les empreintes ne peuvent plus être vérifiées, c'est une anomalie. La
        commande sort avec un code différent de 0.
        / A sealed sale and no key: an anomaly, non-zero exit code.
        """
        self._vendre_un_jus_en_especes()

        with patch.object(LaboutikConfiguration, "get_hmac_key", return_value=None):
            texte_de_la_sortie, code_de_sortie = lancer_la_commande(
                "verify_integrity", f"--schema={self.tenant.schema_name}"
            )

        assert code_de_sortie != 0, texte_de_la_sortie
        assert "Pas de cle HMAC alors que des ventes sont scellees" in (
            texte_de_la_sortie
        )

    def test_verify_integrity_sans_schema_verifie_tous_les_lieux(self):
        """
        Sans `--schema`, la commande vérifie TOUS les lieux (comme `verify_clotures`).
        Les vérifications sont remplacées par un relevé du lieu courant : chaque lieu
        (hors schéma public) est vérifié une fois, le lieu du test compris.
        / Without --schema, every venue is verified once.
        """
        releve_des_lieux = ReleveDesLieuxVerifies()

        with patch.object(LaboutikConfiguration, "get_hmac_key", return_value="cle"):
            with patch(
                "laboutik.integrity.verifier_chaine_ventes",
                side_effect=releve_des_lieux.noter_le_lieu_courant,
            ):
                with patch(
                    "comptabilite.integrite.verifier_chaine_clotures", return_value=[]
                ):
                    lancer_la_commande("verify_integrity")

        nombre_de_lieux = Client.objects.exclude(schema_name="public").count()
        assert len(releve_des_lieux.lieux_verifies) == nombre_de_lieux
        assert self.tenant.schema_name in releve_des_lieux.lieux_verifies
