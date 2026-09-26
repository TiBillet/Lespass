"""
Recharge temps (TM) desactivee : jamais proposee ni vendue en caisse.
/ Time top-up (TM) disabled: never offered nor sold at the POS.

LOCALISATION : tests/pytest/test_laboutik_recharge_temps_desactivee.py

La recharge temps est retiree de METHODES_RECHARGE (laboutik/views.py).
Un produit TM encore present en base ne doit donc :
- ni s'afficher en tuile (_construire_donnees_articles) ;
- ni etre accepte dans un panier poste a la main (_extraire_articles_du_panier).
Sans ces filtres, il serait vendu comme un article normal, paye en euros,
sans crediter de temps sur la carte.
/ A TM product still in the database must not show as a tile nor be
accepted in a hand-made cart: it would be paid in euros with no time credit.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_laboutik_recharge_temps_desactivee.py -v
"""

import pytest
from decimal import Decimal

from django.http import QueryDict
from django_tenants.utils import tenant_context

from Customers.models import Client

PREFIXE = "zz_test_recharge_temps"


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name="lespass")


@pytest.fixture(scope="module")
def donnees_recharge_temps(tenant):
    """
    Un produit TM (comme ceux crees avant la desactivation) avec un tarif a 5 €,
    dans un point de vente.
    / A TM product (like those created before disabling) with a 5 € price, in a POS.
    """
    from BaseBillet.models import Price, Product
    from laboutik.models import PointDeVente

    with tenant_context(tenant):
        produit_temps, _created = Product.objects.get_or_create(
            name=f"{PREFIXE} Recharge temps",
            defaults={
                "categorie_article": Product.NONE,
                "methode_caisse": Product.RECHARGE_TEMPS,
                "publish": True,
            },
        )
        tarif_cinq_euros, _created = Price.objects.get_or_create(
            product=produit_temps,
            name=f"{PREFIXE} 5",
            defaults={"prix": Decimal("5.00"), "publish": True, "order": 1},
        )
        point_de_vente, _created = PointDeVente.objects.get_or_create(
            name=f"{PREFIXE} PV",
            defaults={
                "comportement": PointDeVente.DIRECT,
                "accepte_especes": True,
                "poid_liste": 9999,
            },
        )
        point_de_vente.products.add(produit_temps)
        return {
            "produit": produit_temps,
            "tarif": tarif_cinq_euros,
            "pv": point_de_vente,
        }


def test_tuiles_ne_montrent_pas_la_recharge_temps(tenant, donnees_recharge_temps):
    """
    Le produit TM est dans le point de vente, mais aucune tuile ne l'affiche.
    / The TM product is in the POS, but no tile shows it.
    """
    from laboutik.views import _construire_donnees_articles

    produit_temps = donnees_recharge_temps["produit"]
    with tenant_context(tenant):
        articles = _construire_donnees_articles(donnees_recharge_temps["pv"])

    identifiants_des_tuiles = []
    for article in articles:
        identifiants_des_tuiles.append(article["id"])

    assert str(produit_temps.uuid) not in identifiants_des_tuiles


def test_panier_poste_a_la_main_refuse_la_recharge_temps(
    tenant, donnees_recharge_temps
):
    """
    Un POST force avec le produit TM ne donne aucun article a encaisser.
    / A forged POST with the TM product yields no article to charge.
    """
    from laboutik.views import _extraire_articles_du_panier

    produit_temps = donnees_recharge_temps["produit"]
    tarif_cinq_euros = donnees_recharge_temps["tarif"]
    donnees_post = QueryDict(mutable=True)
    donnees_post[f"repid-{produit_temps.uuid}--{tarif_cinq_euros.uuid}"] = "1"

    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(
            donnees_post, donnees_recharge_temps["pv"]
        )

    assert articles == []
