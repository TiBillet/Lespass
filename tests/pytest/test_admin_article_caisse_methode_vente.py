"""
Tests de l'admin des produits de caisse : la méthode de caisse est figée.
/ Tests of the POS product admin: the POS method is locked.

LOCALISATION : tests/pytest/test_admin_article_caisse_methode_vente.py

RÈGLE MÉTIER TESTÉE
Pour l'instant, l'admin ne crée que des articles de caisse « Vente ».
- Le champ « Méthode de caisse » est caché sur la fiche.
- Un nouvel article est toujours enregistré en « Vente », quelle que soit la valeur
  envoyée par le navigateur.
- Un article existant garde sa méthode : l'admin ne peut pas la changer.
La règle est dans `POSProductForm.clean_methode_caisse`
(Administration/admin/products.py).
/ For now the admin only creates "Sale" POS items. The field is hidden, a new item is
always "Sale", an existing item keeps its method.

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1). Le lieu, l'administrateur et les données du formulaire viennent de
test_admin_retour_de_consigne.py.
/ Rolled-back transaction per test. Helpers come from test_admin_retour_de_consigne.py.

Lancer / Run : make test ARGS="tests/pytest/test_admin_article_caisse_methode_vente.py"
"""

from types import SimpleNamespace

import pytest
from django_tenants.utils import tenant_context

from BaseBillet.models import POSProduct, Product
from fabriques_panier import (
    client_connecte,
    configuration_modifiee,
    taches_celery_enregistrees,
)
from test_admin_retour_de_consigne import (  # noqa: F401 (fixture autouse)
    _langue_par_defaut_apres_chaque_test,
    administrateur_du_lieu,
    donnees_d_un_produit_de_caisse,
    donnees_des_listes_sous_la_fiche,
    formulaire_rempli_d_un_produit_de_caisse,
)
from test_caisse_ecrit_la_vente import creer_un_article_de_caisse

pytestmark = pytest.mark.django_db

# Page d'ajout d'un produit de caisse dans l'admin.
# / Add page of a POS product in the admin.
URL_D_AJOUT_D_UN_PRODUIT_DE_CAISSE = "/admin/BaseBillet/posproduct/add/"


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée en mémoire (jamais enregistrée, tests/PIEGES.md
    13.22), Celery simulé pendant tout le test (tests/PIEGES.md 13.4).
    / The `lespass` venue, register on in memory only, Celery faked.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees():
                yield SimpleNamespace(tenant=tenant)


def creer_un_article_existant(methode_caisse):
    """
    Un article de caisse déjà en base, avec la méthode demandée.
    Rendu comme POSProduct, le modèle du formulaire de l'admin.
    / A POS item already in the database, with the given method, as a POSProduct.

    :param methode_caisse: `Product.methode_caisse` (VENTE, RECHARGE_EUROS…)
    """
    article = creer_un_article_de_caisse(
        "article existant",
        prix_en_euros="2.00",
        taux_tva="20.00",
        methode_caisse=methode_caisse,
    )
    return POSProduct.objects.get(pk=article.produit.pk)


def test_la_page_d_ajout_cache_la_methode_de_caisse(lieu):
    """
    La page d'ajout ne montre pas de liste « Méthode de caisse » : le champ est un
    champ caché, qui vaut « Vente ».
    / The add page shows no "POS method" list: the field is hidden, set to "Sale".
    """
    administrateur = administrateur_du_lieu(lieu)
    client_de_l_admin = client_connecte(administrateur)

    reponse = client_de_l_admin.get(URL_D_AJOUT_D_UN_PRODUIT_DE_CAISSE)

    assert reponse.status_code == 200
    champ_affiche = reponse.context["adminform"].form["methode_caisse"]
    assert champ_affiche.is_hidden
    assert champ_affiche.value() == Product.VENTE
    html_de_la_page = reponse.content.decode()
    assert '<select name="methode_caisse"' not in html_de_la_page


def test_un_nouvel_article_est_enregistre_en_vente_meme_si_le_navigateur_envoie_autre_chose(
    lieu,
):
    """
    L'administrateur enregistre la VRAIE page d'ajout, avec « Recharge euros » forcé
    dans le champ caché. L'article est créé en « Vente ».
    / The admin posts the REAL add page with "Euro top-up" forced in the hidden field.
    The item is created as "Sale".
    """
    administrateur = administrateur_du_lieu(lieu)
    client_de_l_admin = client_connecte(administrateur)
    donnees = donnees_d_un_produit_de_caisse(Product.RECHARGE_EUROS)
    nom_du_produit = donnees["name"]
    donnees.update(donnees_des_listes_sous_la_fiche(administrateur, []))

    reponse = client_de_l_admin.post(URL_D_AJOUT_D_UN_PRODUIT_DE_CAISSE, donnees)

    article_cree = Product.objects.filter(name=nom_du_produit).first()
    assert article_cree is not None, (
        f"L'article n'a pas été créé (statut {reponse.status_code})."
    )
    assert article_cree.methode_caisse == Product.VENTE


def test_un_article_vente_existant_ne_peut_pas_devenir_une_recharge(lieu):
    """
    Un article « Vente » existant est enregistré avec « Recharge euros » forcé dans le
    champ caché. Il reste « Vente ».
    / An existing "Sale" item posted with "Euro top-up" stays "Sale".
    """
    administrateur = administrateur_du_lieu(lieu)
    article_vente = creer_un_article_existant(Product.VENTE)
    donnees = donnees_d_un_produit_de_caisse(Product.RECHARGE_EUROS)

    formulaire = formulaire_rempli_d_un_produit_de_caisse(
        administrateur, donnees, produit=article_vente
    )
    assert formulaire.is_valid(), formulaire.errors
    formulaire.save()

    article_vente.refresh_from_db()
    assert article_vente.methode_caisse == Product.VENTE


def test_une_recharge_existante_garde_sa_methode(lieu):
    """
    Une recharge existante est enregistrée avec « Vente » dans le champ caché. Elle
    reste une recharge : l'admin ne change jamais la méthode d'un article existant.
    / An existing top-up posted with "Sale" stays a top-up.
    """
    administrateur = administrateur_du_lieu(lieu)
    recharge = creer_un_article_existant(Product.RECHARGE_EUROS)
    donnees = donnees_d_un_produit_de_caisse(Product.VENTE)

    formulaire = formulaire_rempli_d_un_produit_de_caisse(
        administrateur, donnees, produit=recharge
    )

    assert formulaire.is_valid(), formulaire.errors
    assert formulaire.cleaned_data["methode_caisse"] == Product.RECHARGE_EUROS
