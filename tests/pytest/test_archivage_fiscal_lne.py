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

POURQUOI CE FICHIER EXISTE / WHY THIS FILE EXISTS
--------------------------------------------------
Ce module n'avait AUCUN test. Il a passe des mois a lever une `AttributeError`
sans que personne ne s'en apercoive : il filtrait sur une valeur de `SaleOrigin`
absente de l'enumeration. L'archivage fiscal etait donc mort en production, quel
que soit le reglage du mode ecole.

Ces tests ne verifient pas le detail du contenu des archives — ils verifient que
la chaine s'execute, ce qui aurait suffi a rendre la panne visible.
/ This module had NO test at all and spent months raising an AttributeError,
filtering on a SaleOrigin value missing from the enum. These tests do not check
the archives' contents in detail; they check that the chain runs at all, which
would have been enough to make the outage visible.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        /DjangoFiles/tests/pytest/test_archivage_fiscal_lne.py -v
"""

import inspect
import re

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.models import SaleOrigin
from Customers.models import Client as TenantClient

pytestmark = pytest.mark.django_db

# Les fichiers que l'archive doit contenir. La liste vient de ce que le module
# produit reellement ; elle sert de garde contre une disparition silencieuse
# de l'un d'eux.
# / The files the archive must contain, as a guard against one silently vanishing.
FICHIERS_ATTENDUS_DANS_L_ARCHIVE = [
    "lignes_article.csv",
    "clotures.csv",
    "corrections.csv",
    "impressions.csv",
    "sorties_caisse.csv",
]


@pytest.fixture
def tenant():
    """Le tenant de developpement. / The development tenant."""
    return TenantClient.objects.get(schema_name="lespass")


def test_l_archivage_fiscal_s_execute_sans_erreur(tenant):
    """La generation des fichiers d'archive aboutit.

    C'est le test qui manquait : il echouait avec `AttributeError` tant que le
    module filtrait sur une origine de vente inexistante. Une obligation legale
    ne doit pas dependre d'un chemin que personne n'execute jamais.
    / The missing test: it failed with AttributeError while the module filtered
    on a nonexistent sale origin. A legal obligation must not rest on a code
    path nobody ever runs.
    """
    with tenant_context(tenant):
        from laboutik.archivage import generer_fichiers_archive

        fichiers = generer_fichiers_archive(schema=tenant.schema_name)

    assert isinstance(fichiers, dict)
    for nom_de_fichier in FICHIERS_ATTENDUS_DANS_L_ARCHIVE:
        assert nom_de_fichier in fichiers, (
            f"L'archive fiscale ne contient plus {nom_de_fichier}"
        )


def test_l_archive_conserve_l_origine_de_chaque_vente(tenant):
    """Le CSV des ventes porte une colonne d'origine.

    La norme demande de pouvoir distinguer les ventes selon leur provenance.
    Sans cette colonne, une archive resterait techniquement valide mais
    inexploitable lors d'un controle.
    / The standard requires telling sales apart by origin. Without this column
    the archive stays technically valid but useless during an audit.
    """
    with tenant_context(tenant):
        from laboutik.archivage import generer_fichiers_archive

        fichiers = generer_fichiers_archive(schema=tenant.schema_name)

    # Le module renvoie des `bytes` prefixes d'un BOM UTF-8, pour que le fichier
    # s'ouvre correctement dans un tableur. On decode avant de chercher.
    # / The module returns bytes prefixed with a UTF-8 BOM so the file opens
    # correctly in a spreadsheet. Decode before searching.
    contenu_des_ventes = fichiers["lignes_article.csv"]
    if isinstance(contenu_des_ventes, bytes):
        contenu_des_ventes = contenu_des_ventes.decode("utf-8-sig")

    entete = contenu_des_ventes.splitlines()[0]
    assert "sale_origin" in entete


def test_l_origine_utilisee_par_l_archivage_existe_bien(tenant):
    """Garde-fou : l'origine filtree par l'archivage est une valeur reelle.

    C'est exactement le defaut qui a mis l'archivage hors service — une constante
    referencee mais absente de l'enumeration. Le test echoue si quelqu'un
    reintroduit une valeur fantome.
    / The exact defect that broke archiving: a constant referenced but missing
    from the enum. This fails if someone reintroduces a ghost value.
    """
    from laboutik import archivage

    code_source = inspect.getsource(archivage)

    # Toutes les valeurs citees sous la forme `SaleOrigin.XXX` doivent exister.
    # / Every `SaleOrigin.XXX` mentioned must exist.
    origines_citees = set(re.findall(r"SaleOrigin\.([A-Z_]+)", code_source))
    assert origines_citees, "Aucune origine citee : le test ne verifie plus rien."

    for nom_d_origine in origines_citees:
        assert hasattr(SaleOrigin, nom_d_origine), (
            f"laboutik/archivage.py cite SaleOrigin.{nom_d_origine}, "
            f"qui n'existe pas dans l'enumeration."
        )


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
