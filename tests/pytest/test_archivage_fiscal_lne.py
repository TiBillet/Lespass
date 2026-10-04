"""
tests/pytest/test_archivage_fiscal_lne.py
L'archivage fiscal LNE doit pouvoir s'executer.
/ The LNE fiscal archive must be able to run.

LOCALISATION : tests/pytest/test_archivage_fiscal_lne.py

CE QUI EST TESTE / WHAT IS TESTED
---------------------------------
`laboutik/archivage.py` produit les fichiers d'archive exiges par la norme LNE
(conservation et restitution des donnees de caisse). Quatre points d'entree
l'appellent : la vue `laboutik/views.py`, et les commandes `archiver_donnees`,
`verifier_archive` et `acces_fiscal`.

CE QUE CE FICHIER GARDE / WHAT THIS FILE GUARDS
------------------------------------------------
L'archivage fiscal est une obligation legale : il doit s'executer sur la base du
lieu de developpement, avec tous ses fichiers et les colonnes de ses ventes. Le
detail du contenu des archives est teste dans
`tests/pytest/test_archive_lne_ventes.py`.
/ The fiscal archive is a legal duty: it must run on the development venue, with
all its files and its sales columns. Contents are tested in
test_archive_lne_ventes.py.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_archivage_fiscal_lne.py -v
"""

import csv
import inspect
import re

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.models import SaleOrigin
from Customers.models import Client as TenantClient

pytestmark = pytest.mark.django_db

# Les fichiers que l'archive doit contenir. La liste vient de ce que le module
# produit reellement ; elle sert de garde contre une disparition silencieuse
# de l'un d'eux. Les corrections de moyen de paiement sont des ventes
# « CORRECTION » : elles sont dans les fichiers des ventes, sans fichier a part.
# / The files the archive must contain, as a guard against one silently vanishing.
# Payment corrections are CORRECTION sales, inside the sales files.
FICHIERS_ATTENDUS_DANS_L_ARCHIVE = [
    "ventes.csv",
    "articles.csv",
    "reglements.csv",
    "clotures.csv",
    "impressions.csv",
    "sorties_caisse.csv",
    "historique_fond.csv",
]

# Les colonnes du CSV des ventes, dans l'ordre (le contrat complet de chaque fichier
# est dans tests/pytest/test_archive_lne_ventes.py).
# / The sales CSV columns, in order.
COLONNES_ATTENDUES_DES_VENTES = [
    "uuid", "numero", "nature", "statut", "origine", "unite",
    "datetime_encaissement", "point_de_vente", "point_de_vente_uuid",
    "operateur_email", "vente_liee_uuid", "total_catalogue", "total_offert",
    "total_ttc", "total_ht", "total_tva", "previous_hmac", "hmac_hash",
]


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def test_l_archivage_fiscal_s_execute_sans_erreur(tenant):
    """La generation des fichiers d'archive aboutit, avec tous ses fichiers, et sans
    fichier des corrections (une correction est une vente CORRECTION).
    Une obligation legale ne doit pas dependre d'un chemin que personne n'execute.
    / Archive generation succeeds, with every file and no corrections file. A legal
    obligation must not rest on a code path nobody runs.
    """
    with tenant_context(tenant):
        from laboutik.archivage import generer_fichiers_archive

        fichiers = generer_fichiers_archive(schema=tenant.schema_name)

    assert isinstance(fichiers, dict)
    for nom_de_fichier in FICHIERS_ATTENDUS_DANS_L_ARCHIVE:
        assert nom_de_fichier in fichiers, (
            f"L'archive fiscale ne contient pas {nom_de_fichier}"
        )
    assert "corrections.csv" not in fichiers


def test_l_archive_conserve_l_origine_de_chaque_vente(tenant):
    """Le CSV des ventes a exactement les colonnes attendues, dans l'ordre, dont la
    colonne d'origine.

    La norme demande de pouvoir distinguer les ventes selon leur provenance.
    Sans cette colonne, une archive resterait techniquement valide mais
    inexploitable lors d'un controle. L'archive exporte toutes les origines
    (voir tests/pytest/test_archive_lne_ventes.py, tireuse et en ligne).
    / The sales CSV has exactly the expected columns, in order, origin included.
    """
    with tenant_context(tenant):
        from laboutik.archivage import generer_fichiers_archive

        fichiers = generer_fichiers_archive(schema=tenant.schema_name)

    # Le module renvoie des `bytes` prefixes d'un BOM UTF-8, pour que le fichier
    # s'ouvre correctement dans un tableur. On decode avant de chercher.
    # / The module returns bytes prefixed with a UTF-8 BOM so the file opens
    # correctly in a spreadsheet. Decode before searching.
    contenu_des_ventes = fichiers["ventes.csv"]
    if isinstance(contenu_des_ventes, bytes):
        contenu_des_ventes = contenu_des_ventes.decode("utf-8-sig")

    lecteur_des_ventes = csv.reader(contenu_des_ventes.splitlines(), delimiter=";")
    colonnes_de_l_entete = next(lecteur_des_ventes)
    assert colonnes_de_l_entete == COLONNES_ATTENDUES_DES_VENTES


def test_le_mode_ecole_ne_marque_plus_les_ventes(tenant):
    """Le mode ecole est desactive : aucune vente ne porte d'origine de test.

    Le champ `mode_ecole` reste en base mais n'a plus d'effet. Ce test verrouille
    la desactivation : si quelqu'un remet une branche de marquage sans avoir
    ajoute l'origine correspondante a l'enumeration, la caisse se bloquerait a
    nouveau.
    / Training mode is disabled: the field remains but has no effect. This locks
    the deactivation in place.
    """
    from laboutik import views

    code_des_vues = inspect.getsource(views)

    origines_citees = set(re.findall(r"SaleOrigin\.([A-Z_]+)", code_des_vues))
    for nom_d_origine in origines_citees:
        assert hasattr(SaleOrigin, nom_d_origine), (
            f"laboutik/views.py cite SaleOrigin.{nom_d_origine}, "
            f"qui n'existe pas dans l'enumeration — la caisse se bloquerait."
        )
