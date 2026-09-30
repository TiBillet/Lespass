"""
Tests de l'admin des produits de caisse : un « Retour de consigne » doit dire quel
gobelet il rembourse, et ce gobelet doit avoir un prix que la caisse sait rendre.
/ Tests of the POS product admin: a "deposit return" must name the cup it refunds, and
that cup must have a price the register can give back.

LOCALISATION : tests/pytest/test_admin_retour_de_consigne.py

RÈGLE MÉTIER TESTÉE
Le formulaire d'un produit de caisse (`POSProductForm`) refuse d'enregistrer un produit
de méthode « Retour de consigne » :
- sans consigne reliée (`consigne_remboursee` vide) ;
- relié à un gobelet qui n'a AUCUN tarif en euros vendable à la caisse (même règle que
  la caisse, `_tarifs_vendables_a_la_caisse` dans laboutik/views.py).
L'erreur est posée sur le champ `consigne_remboursee`. Un article ordinaire (méthode
« Vente ») n'a pas besoin de consigne reliée.
C'est la première des trois sécurités : la caisse masque aussi la tuile d'un tel retour,
et refuse de l'encaisser.
/ The POS product form refuses a deposit return without a linked cup, or linked to a
cup without a POS-sellable euro price. The error sits on `consigne_remboursee`.

Spécification : TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-B-caisse.md (§3)
et CHANTIER-05-montants-entiers.md (D11).

SIMULATIONS
Chaque test est marqué `django_db` : la transaction est annulée à la fin (tests/PIEGES.md
13.1), rien ne reste en base de dev. La caisse est activée par `configuration_modifiee()`,
jamais enregistrée (tests/PIEGES.md 13.22). Celery est simulé (tests/PIEGES.md 13.4).
/ Rolled-back transaction per test. Register module on in memory only. Celery faked.

Lancer / Run : make test ARGS="tests/pytest/test_admin_retour_de_consigne.py"
"""

from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from Administration.admin.products import POSProductAdmin
from Administration.admin.site import staff_admin_site
from AuthBillet.models import TibilletUser
from BaseBillet.models import POSProduct, Price, Product
from fabriques_panier import (
    client_connecte,
    configuration_modifiee,
    identifiant_unique,
    taches_celery_enregistrees,
)
from test_caisse_ecrit_la_vente import creer_un_article_de_caisse

pytestmark = pytest.mark.django_db

# Page d'ajout d'un produit de caisse dans l'admin.
# / Add page of a POS product in the admin.
URL_D_AJOUT_D_UN_PRODUIT_DE_CAISSE = "/admin/BaseBillet/posproduct/add/"

# Début du nom de tout ce que ces tests créent.
# / Prefix of everything these tests create.
PREFIXE_DES_TESTS = "TEST_admin_retour_consigne"


@pytest.fixture(autouse=True)
def _langue_par_defaut_apres_chaque_test():
    """Les signaux activent la langue du lieu sans la remettre (tests/PIEGES.md, 10.5).
    / Signals activate the venue language without resetting it."""
    from django.utils import translation

    yield
    translation.deactivate()


@pytest.fixture
def lieu(tenant):
    """
    Le lieu `lespass`, caisse activée en mémoire, Celery simulé pendant tout le test.
    / The `lespass` venue, register on in memory, Celery faked for the whole test.
    """
    with tenant_context(tenant):
        with configuration_modifiee(module_caisse=True, module_monnaie_locale=True):
            with taches_celery_enregistrees() as taches_demandees:
                yield SimpleNamespace(
                    tenant=tenant,
                    taches_demandees=taches_demandees,
                )


# --------------------------------------------------------------------------
# L'administrateur et le formulaire de l'admin
# / The admin user and the admin form
# --------------------------------------------------------------------------


def administrateur_du_lieu(lieu):
    """
    L'utilisateur `admin@admin.com`, administrateur du lieu. Créé s'il n'existe pas : la
    transaction du test l'efface ensuite.
    / The `admin@admin.com` user, venue admin. Created if missing, rolled back after.
    """
    administrateur, _administrateur_cree = TibilletUser.objects.get_or_create(
        email="admin@admin.com",
        defaults={"username": "admin@admin.com", "is_active": True},
    )
    administrateur.client_admin.add(lieu.tenant)
    return administrateur


def admin_des_produits_de_caisse():
    """L'admin des produits de caisse, sur le site d'admin du lieu.
    / The POS product admin, on the venue admin site."""
    return POSProductAdmin(POSProduct, staff_admin_site)


def formulaire_rempli_d_un_produit_de_caisse(administrateur, donnees):
    """
    Le formulaire que l'admin affiche pour AJOUTER un produit de caisse, rempli avec
    `donnees`. La classe du formulaire est construite par l'admin lui-même (`get_form`) :
    elle contient les champs des sections de l'admin, dont `consigne_remboursee`.
    / The form the admin shows to ADD a POS product, filled with `donnees`. The form
    class is built by the admin itself, with the fields of its sections.
    """
    requete = RequestFactory().post("/")
    requete.user = administrateur
    ClasseDuFormulaire = admin_des_produits_de_caisse().get_form(requete, obj=None)
    return ClasseDuFormulaire(data=donnees)


def donnees_d_un_produit_de_caisse(methode_caisse, consigne_remboursee=None):
    """
    Les champs de la fiche d'un produit de caisse, comme le navigateur les envoie.
    / The fields of a POS product page, as the browser sends them.

    :param methode_caisse: `Product.methode_caisse` (VENTE, RETOUR_CONSIGNE…)
    :param consigne_remboursee: le Product gobelet relié, ou None (champ vide)
    """
    if consigne_remboursee is None:
        valeur_de_la_consigne_remboursee = ""
    else:
        valeur_de_la_consigne_remboursee = str(consigne_remboursee.pk)

    return {
        "name": f"{PREFIXE_DES_TESTS} {identifiant_unique()}",
        "categorie_article": Product.NONE,
        "methode_caisse": methode_caisse,
        "consigne_remboursee": valeur_de_la_consigne_remboursee,
        "categorie_pos": "",
        "tva": "",
        "prix_achat": "0",
        "palette_pos": "",
        "couleur_texte_pos": "",
        "couleur_fond_pos": "",
        "icon_pos": "",
        "poids": "0",
        "publish": "on",
    }


def creer_un_gobelet(avec_tarif_en_euros_vendable):
    """
    Un gobelet consigné vendu 1,00 € (méthode « Vente »).
    Sans tarif vendable : son seul tarif en euros est dépublié (`publish=False`), la
    caisse ne le vend donc pas.
    / A deposit cup sold 1.00 €. Without a sellable price: its only euro price is
    unpublished, so the register does not sell it.
    """
    gobelet = creer_un_article_de_caisse(
        "gobelet consigne", prix_en_euros="1.00", taux_tva="20.00"
    )
    if not avec_tarif_en_euros_vendable:
        Price.objects.filter(pk=gobelet.tarif.pk).update(publish=False)
    return gobelet.produit


# --------------------------------------------------------------------------
# Le formulaire refuse un retour de consigne mal configuré
# / The form refuses a badly configured deposit return
# --------------------------------------------------------------------------


def test_admin_refuse_un_retour_de_consigne_sans_consigne_reliee(lieu):
    """
    Un produit « Retour de consigne » sans consigne reliée : le formulaire est refusé,
    avec une erreur sur le champ « Rembourse la consigne ».
    / A deposit return without a linked deposit: the form is refused, with an error on
    the `consigne_remboursee` field.
    """
    administrateur = administrateur_du_lieu(lieu)
    donnees = donnees_d_un_produit_de_caisse(Product.RETOUR_CONSIGNE)

    formulaire = formulaire_rempli_d_un_produit_de_caisse(administrateur, donnees)

    assert not formulaire.is_valid()
    assert "consigne_remboursee" in formulaire.errors


def test_admin_refuse_un_retour_relie_a_un_gobelet_sans_tarif_en_euros(lieu):
    """
    Le retour est relié à un gobelet dont le seul tarif en euros n'est pas vendable à la
    caisse (dépublié) : la caisse ne saurait pas quel prix rendre. Le formulaire est
    refusé, avec une erreur sur le champ « Rembourse la consigne ».
    / The return is linked to a cup whose only euro price is not sellable at the
    register: the form is refused, with an error on `consigne_remboursee`.
    """
    administrateur = administrateur_du_lieu(lieu)
    gobelet_sans_tarif_vendable = creer_un_gobelet(avec_tarif_en_euros_vendable=False)
    donnees = donnees_d_un_produit_de_caisse(
        Product.RETOUR_CONSIGNE, consigne_remboursee=gobelet_sans_tarif_vendable
    )

    formulaire = formulaire_rempli_d_un_produit_de_caisse(administrateur, donnees)

    assert not formulaire.is_valid()
    assert "consigne_remboursee" in formulaire.errors


# --------------------------------------------------------------------------
# Le formulaire accepte ce qui est bien configuré (témoins)
# / The form accepts what is well configured (controls)
# --------------------------------------------------------------------------


def test_admin_accepte_un_retour_relie_a_un_gobelet_avec_tarif_en_euros(lieu):
    """
    Le retour est relié à un gobelet qui a un tarif en euros vendable à la caisse : le
    formulaire est accepté. Témoin : une validation qui refuserait tout ferait tomber ce
    test.
    / The return is linked to a cup with a sellable euro price: the form is accepted.
    Control: a validation that refuses everything would fail this test.
    """
    administrateur = administrateur_du_lieu(lieu)
    gobelet = creer_un_gobelet(avec_tarif_en_euros_vendable=True)
    donnees = donnees_d_un_produit_de_caisse(
        Product.RETOUR_CONSIGNE, consigne_remboursee=gobelet
    )

    formulaire = formulaire_rempli_d_un_produit_de_caisse(administrateur, donnees)

    assert formulaire.is_valid(), formulaire.errors


def test_admin_vente_ordinaire_sans_consigne_reliee_acceptee(lieu):
    """
    Un article ordinaire (méthode « Vente ») n'a pas de consigne reliée : le formulaire
    est accepté.
    / An ordinary item (method "Sale") has no linked deposit: the form is accepted.
    """
    administrateur = administrateur_du_lieu(lieu)
    donnees = donnees_d_un_produit_de_caisse(Product.VENTE)

    formulaire = formulaire_rempli_d_un_produit_de_caisse(administrateur, donnees)

    assert formulaire.is_valid(), formulaire.errors


# --------------------------------------------------------------------------
# La vraie page d'ajout de l'admin : rien n'est créé
# / The real admin add page: nothing is created
# --------------------------------------------------------------------------


def donnees_des_listes_sous_la_fiche(administrateur, tarifs_saisis):
    """
    Les champs des listes affichées sous la fiche d'ajout (tarifs, stock), comme le
    navigateur les envoie. Chaque liste a quatre champs de gestion (`<préfixe>-TOTAL_FORMS`…) ;
    l'admin les exige même quand la liste est vide. Les préfixes sont lus sur l'admin
    lui-même : le test n'a pas à les deviner.
    / The fields of the lists under the add page (prices, stock), as the browser sends
    them. The prefixes are read from the admin itself.

    :param tarifs_saisis: liste de dicts {champ: valeur} pour la liste des tarifs
    """
    requete = RequestFactory().get("/")
    requete.user = administrateur
    listes_de_la_page_d_ajout = (
        admin_des_produits_de_caisse().get_formsets_with_inlines(requete, None)
    )
    donnees = {}
    for ClasseDeLaListe, liste_sous_la_fiche in listes_de_la_page_d_ajout:
        prefixe = ClasseDeLaListe.get_default_prefix()
        liste_des_tarifs = liste_sous_la_fiche.model is Price
        if liste_des_tarifs:
            lignes_saisies = tarifs_saisis
        else:
            lignes_saisies = []

        donnees[f"{prefixe}-TOTAL_FORMS"] = str(len(lignes_saisies))
        donnees[f"{prefixe}-INITIAL_FORMS"] = "0"
        donnees[f"{prefixe}-MIN_NUM_FORMS"] = "0"
        donnees[f"{prefixe}-MAX_NUM_FORMS"] = "1000"
        numero_de_ligne = 0
        for champs_de_la_ligne in lignes_saisies:
            for nom_du_champ, valeur in champs_de_la_ligne.items():
                donnees[f"{prefixe}-{numero_de_ligne}-{nom_du_champ}"] = valeur
            numero_de_ligne = numero_de_ligne + 1
    return donnees


def test_admin_post_d_un_retour_sans_consigne_reliee_ne_cree_rien(lieu):
    """
    L'administrateur `admin@admin.com` remplit la VRAIE page d'ajout d'un produit de
    caisse : un « Retour de consigne » avec un tarif à −1,00 €, sans consigne reliée, et
    l'enregistre. Aucun produit n'est créé ; la page revient avec une erreur sur le champ
    « Rembourse la consigne ».
    Ce test passe par la page affichée : il prouve que le champ est bien dans le
    formulaire de l'admin, et que l'erreur empêche l'enregistrement.
    L'erreur de la consigne est la SEULE erreur de la page : un autre champ manquant ne
    peut pas faire passer ce test à tort.
    / `admin@admin.com` posts the REAL add page: a deposit return with a −1.00 € price,
    no linked deposit. No product is created; the page comes back with an error on
    `consigne_remboursee`, and it is the ONLY error of the page.
    """
    administrateur = administrateur_du_lieu(lieu)
    client_de_l_admin = client_connecte(administrateur)
    donnees = donnees_d_un_produit_de_caisse(Product.RETOUR_CONSIGNE)
    nom_du_produit = donnees["name"]
    tarif_du_retour = {
        "name": "Gobelet",
        "prix": "-1.00",
        "publish": "on",
        "order": "100",
    }
    donnees.update(donnees_des_listes_sous_la_fiche(administrateur, [tarif_du_retour]))

    reponse = client_de_l_admin.post(URL_D_AJOUT_D_UN_PRODUIT_DE_CAISSE, donnees)

    assert not Product.objects.filter(name=nom_du_produit).exists(), (
        "Le retour de consigne sans consigne reliée a été enregistré."
    )
    assert reponse.status_code == 200
    html_de_la_page = reponse.content.decode()
    assert 'name="consigne_remboursee"' in html_de_la_page

    formulaire_affiche = reponse.context["adminform"].form
    assert list(formulaire_affiche.errors.keys()) == ["consigne_remboursee"]
    for liste_sous_la_fiche in reponse.context["inline_admin_formsets"]:
        assert liste_sous_la_fiche.formset.is_valid(), (
            liste_sous_la_fiche.formset.errors
        )
