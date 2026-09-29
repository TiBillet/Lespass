"""
Les pages publiques des adhesions s'affichent et ne montrent que des adhesions.
/ Public membership pages render and only show membership products.

LOCALISATION : tests/pytest/test_membership_pages_publiques.py

Vues testees : BaseBillet/views.py, MembershipMVT.list, .embed et .retrieve.
Elles lisent les produits via MembershipProduct.objects : le manager
(MembershipProductManager, BaseBillet/models.py) ne garde que categorie_article=ADHESION.

Pourquoi ce test : un refactor a casse /memberships/ (NameError sur `products`)
sans qu'aucun test ne le voie, car aucun test n'appelait cette page.
/ Why: a refactor broke /memberships/ (NameError) and no test called the page.
"""

import uuid as uuid_module
from decimal import Decimal

import pytest
from django.test import Client as ClientDjango
from django_tenants.utils import tenant_context

from BaseBillet.models import Price, Product


@pytest.fixture
def adhesion_et_billet_publies(tenant):
    """
    Cree une adhesion publiee (avec un tarif en euros) et un billet publie.
    Le billet sert de temoin : il ne doit jamais apparaitre sur les pages adhesions.
    Les deux produits sont supprimes a la fin du test.
    / Creates a published membership (euro price) and a published ticket.
    The ticket must never appear on membership pages. Both are deleted afterwards.
    """
    suffixe_unique = uuid_module.uuid4().hex[:8]
    with tenant_context(tenant):
        produit_adhesion = Product.objects.create(
            name=f"TEST adhesion page publique {suffixe_unique}",
            categorie_article=Product.ADHESION,
            publish=True,
        )
        Price.objects.create(
            product=produit_adhesion,
            name="Annuelle",
            prix=Decimal("15.00"),
            publish=True,
        )
        produit_billet = Product.objects.create(
            name=f"TEST billet temoin {suffixe_unique}",
            categorie_article=Product.BILLET,
            publish=True,
        )

    yield produit_adhesion, produit_billet

    with tenant_context(tenant):
        # On ne supprime pas : sous pytest, le post_delete de django-stdimage
        # plante sur un produit sans image et annule la suppression
        # (cf. tests/PIEGES.md 10.1). On depublie et on archive a la place.
        # update() ne declenche aucun signal. Les noms sont uniques.
        # / No delete: stdimage's post_delete crashes and rolls it back under
        # pytest. Unpublish and archive instead; update() fires no signal.
        Product.objects.filter(pk__in=[produit_adhesion.pk, produit_billet.pk]).update(
            publish=False,
            archive=True,
        )


def test_la_page_liste_des_adhesions_repond_et_ne_montre_que_les_adhesions(adhesion_et_billet_publies):
    """GET /memberships/ repond 200, montre l'adhesion, pas le billet.
    / GET /memberships/ returns 200, shows the membership, not the ticket."""
    produit_adhesion, produit_billet = adhesion_et_billet_publies
    navigateur = ClientDjango(HTTP_HOST="lespass.tibillet.localhost")

    reponse = navigateur.get("/memberships/")

    assert reponse.status_code == 200, reponse.status_code
    contenu = reponse.content.decode()
    assert produit_adhesion.name in contenu
    assert produit_billet.name not in contenu


def test_la_page_embed_des_adhesions_repond_et_ne_montre_que_les_adhesions(adhesion_et_billet_publies):
    """GET /memberships/embed/ repond 200, montre l'adhesion, pas le billet.
    / GET /memberships/embed/ returns 200, shows the membership, not the ticket."""
    produit_adhesion, produit_billet = adhesion_et_billet_publies
    navigateur = ClientDjango(HTTP_HOST="lespass.tibillet.localhost")

    reponse = navigateur.get("/memberships/embed/")

    assert reponse.status_code == 200, reponse.status_code
    contenu = reponse.content.decode()
    assert produit_adhesion.name in contenu
    assert produit_billet.name not in contenu


def test_la_page_detail_d_une_adhesion_repond(adhesion_et_billet_publies):
    """GET /memberships/<uuid>/ repond 200 et montre l'adhesion.
    / GET /memberships/<uuid>/ returns 200 and shows the membership."""
    produit_adhesion, _produit_billet = adhesion_et_billet_publies
    navigateur = ClientDjango(HTTP_HOST="lespass.tibillet.localhost")

    reponse = navigateur.get(f"/memberships/{produit_adhesion.uuid}/")

    assert reponse.status_code == 200, reponse.status_code
    assert produit_adhesion.name in reponse.content.decode()
