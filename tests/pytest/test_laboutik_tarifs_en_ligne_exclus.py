"""
Tarifs reserves au paiement en ligne : jamais proposes en caisse.
/ Online-only prices: never offered at the POS.

LOCALISATION : tests/pytest/test_laboutik_tarifs_en_ligne_exclus.py

Un tarif a paiement recurrent (abonnement Stripe, prelevement SEPA) ou a
validation manuelle ne peut pas etre vendu par LaBoutik. Il ne doit :
- ni s'afficher en tuile (_construire_donnees_articles) ;
- ni etre accepte dans un panier poste a la main (_extraire_articles_du_panier).
/ A recurring or manual-validation price can't be sold by LaBoutik: no tile,
and a hand-made POST is ignored.
"""

import pytest
from decimal import Decimal

from django.http import QueryDict
from django_tenants.utils import tenant_context

from Customers.models import Client

PREFIXE = "zz_test_tarifs_en_ligne"


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture(scope="module")
def donnees_tarifs(tenant):
    """
    Un produit de vente avec trois tarifs : normal, recurrent, validation manuelle.
    Un point de vente qui contient ce produit.
    / A sale product with three prices (normal, recurring, manual validation)
    and a POS holding it.
    """
    from BaseBillet.models import Price, Product
    from laboutik.models import PointDeVente

    with tenant_context(tenant):
        produit, _created = Product.objects.get_or_create(
            name=f"{PREFIXE} Produit",
            defaults={
                "categorie_article": Product.NONE,
                "methode_caisse": Product.VENTE,
                "publish": True,
            },
        )
        tarif_normal, _created = Price.objects.get_or_create(
            product=produit,
            name=f"{PREFIXE} Normal",
            defaults={"prix": Decimal("10.00"), "publish": True, "order": 1},
        )
        tarif_recurrent, _created = Price.objects.get_or_create(
            product=produit,
            name=f"{PREFIXE} Recurrent",
            defaults={
                "prix": Decimal("12.00"),
                "publish": True,
                "order": 2,
                "recurring_payment": True,
            },
        )
        tarif_validation_manuelle, _created = Price.objects.get_or_create(
            product=produit,
            name=f"{PREFIXE} Validation manuelle",
            defaults={
                "prix": Decimal("14.00"),
                "publish": True,
                "order": 3,
                "manual_validation": True,
            },
        )
        point_de_vente, _created = PointDeVente.objects.get_or_create(
            name=f"{PREFIXE} PV",
            defaults={
                "comportement": PointDeVente.DIRECT,
                "accepte_especes": True,
                "poid_liste": 9999,
            },
        )
        point_de_vente.products.add(produit)
        return {
            "produit": produit,
            "tarif_normal": tarif_normal,
            "tarif_recurrent": tarif_recurrent,
            "tarif_validation_manuelle": tarif_validation_manuelle,
            "pv": point_de_vente,
        }


def _article_du_produit(point_de_vente, produit):
    """
    Retrouve la tuile du produit dans les articles du PV (None si absente).
    / Finds the product tile among the POS articles (None if missing).
    """
    from laboutik.views import _construire_donnees_articles

    articles = _construire_donnees_articles(point_de_vente)
    for article in articles:
        if article["id"] == str(produit.uuid):
            return article
    return None


def test_tuiles_ne_montrent_pas_les_tarifs_en_ligne(tenant, donnees_tarifs):
    """
    Seul le tarif normal reste : la tuile n'est plus multi-tarif
    et affiche 10 €.
    / Only the normal price is left: single-price tile at 10 €.
    """
    with tenant_context(tenant):
        article = _article_du_produit(donnees_tarifs["pv"], donnees_tarifs["produit"])

    assert article is not None
    assert article["multi_tarif"] is False
    assert article["prix"] == 1000
    assert article["tarifs"] == []


def test_panier_poste_a_la_main_ignore_un_tarif_recurrent(tenant, donnees_tarifs):
    from laboutik.views import _extraire_articles_du_panier

    produit = donnees_tarifs["produit"]
    tarif_recurrent = donnees_tarifs["tarif_recurrent"]
    donnees_post = QueryDict(mutable=True)
    donnees_post[f"repid-{produit.uuid}--{tarif_recurrent.uuid}"] = "1"

    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_tarifs["pv"])

    assert articles == []
