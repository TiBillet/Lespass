"""
Vente au poids/mesure : le serveur recalcule le prix, il ignore le montant du JS.
/ Weight/volume sale: the server recomputes the price, it ignores the JS amount.

LOCALISATION : tests/pytest/test_poids_mesure_prix_serveur.py

Avant, _extraire_articles_du_panier acceptait tel quel le montant "custom-..."
calcule par tarif.js. Un client modifie pouvait vendre 1 kg a 1 centime.
Maintenant, le prix vient de la quantite saisie ("weight-...") et du prix
de reference du tarif (au kg ou au litre).
/ Before, the JS amount was trusted. Now the price comes from the entered
quantity and the price per kg / per litre.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_poids_mesure_prix_serveur.py -v
"""

import pytest
from decimal import Decimal

from django.http import QueryDict
from django_tenants.utils import tenant_context

from Customers.models import Client

PREFIXE = "zz_test_poids_prix_serveur"


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name="lespass")


def _creer_produit_au_poids(nom, prix_de_reference, unite):
    """
    Cree un produit vendu au poids/mesure, son tarif et son stock.
    / Creates a weight/volume product, its price and its stock.
    """
    from BaseBillet.models import Price, Product
    from inventaire.models import Stock

    produit, _created = Product.objects.get_or_create(
        name=f"{PREFIXE} {nom}",
        defaults={
            "categorie_article": Product.NONE,
            "methode_caisse": Product.VENTE,
            "publish": True,
        },
    )
    tarif, _created = Price.objects.get_or_create(
        product=produit,
        name=f"{PREFIXE} {nom} tarif",
        defaults={
            "prix": prix_de_reference,
            "publish": True,
            "order": 1,
            "poids_mesure": True,
        },
    )
    Stock.objects.get_or_create(
        product=produit,
        defaults={
            "quantite": 1000000,
            "unite": unite,
            "autoriser_vente_hors_stock": True,
        },
    )
    return produit, tarif


@pytest.fixture(scope="module")
def donnees_poids(tenant):
    """
    Du comte a 20 €/kg (stock en grammes) et du vin a 8 €/L (stock en cl),
    dans un point de vente.
    / Cheese at 20 €/kg (grams) and wine at 8 €/L (cl), in a POS.
    """
    from inventaire.models import UniteStock
    from laboutik.models import PointDeVente

    with tenant_context(tenant):
        comte, tarif_comte = _creer_produit_au_poids(
            "Comte", Decimal("20.00"), UniteStock.GR
        )
        vin, tarif_vin = _creer_produit_au_poids(
            "Vin vrac", Decimal("8.00"), UniteStock.CL
        )
        point_de_vente, _created = PointDeVente.objects.get_or_create(
            name=f"{PREFIXE} PV",
            defaults={
                "comportement": PointDeVente.DIRECT,
                "accepte_especes": True,
                "poid_liste": 9999,
            },
        )
        point_de_vente.products.add(comte, vin)
        return {
            "comte": comte,
            "tarif_comte": tarif_comte,
            "vin": vin,
            "tarif_vin": tarif_vin,
            "pv": point_de_vente,
        }


def _panier_au_poids(produit, tarif, quantite_saisie, montant_envoye_par_le_js):
    """
    Construit le POST d'une ligne au poids, comme addition.js.
    None = champ absent.
    / Builds the POST of a weighed line, like addition.js. None = field missing.
    """
    identifiant_de_ligne = f"{produit.uuid}--{tarif.uuid}--1"
    donnees_post = QueryDict(mutable=True)
    donnees_post[f"repid-{identifiant_de_ligne}"] = "1"
    if quantite_saisie is not None:
        donnees_post[f"weight-{identifiant_de_ligne}"] = str(quantite_saisie)
    if montant_envoye_par_le_js is not None:
        donnees_post[f"custom-{identifiant_de_ligne}"] = str(montant_envoye_par_le_js)
    return donnees_post


def test_350_grammes_a_20_euros_le_kilo_coutent_700_centimes(tenant, donnees_poids):
    from laboutik.views import _extraire_articles_du_panier

    donnees_post = _panier_au_poids(
        donnees_poids["comte"], donnees_poids["tarif_comte"], 350, 700
    )
    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_poids["pv"])

    assert len(articles) == 1
    assert articles[0]["prix_centimes"] == 700
    assert articles[0]["weight_amount"] == 350


def test_montant_falsifie_par_le_client_est_remplace_par_le_montant_serveur(
    tenant, donnees_poids
):
    """
    Le JS envoie 1 centime pour 350 g : le serveur garde 700 centimes.
    / The JS sends 1 cent for 350 g: the server keeps 700 cents.
    """
    from laboutik.views import _extraire_articles_du_panier

    donnees_post = _panier_au_poids(
        donnees_poids["comte"], donnees_poids["tarif_comte"], 350, 1
    )
    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_poids["pv"])

    assert len(articles) == 1
    assert articles[0]["prix_centimes"] == 700
    assert articles[0]["custom_amount_centimes"] == 700


def test_ligne_au_poids_sans_quantite_saisie_est_ignoree(tenant, donnees_poids):
    """
    Sans quantite, on ne peut pas calculer le prix : l'article est ignore
    (avant, il etait vendu au prix d'un kilo entier).
    / Without a quantity the price can't be computed: the article is ignored.
    """
    from laboutik.views import _extraire_articles_du_panier

    donnees_post = _panier_au_poids(
        donnees_poids["comte"], donnees_poids["tarif_comte"], None, 700
    )
    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_poids["pv"])

    assert articles == []


def test_ligne_au_poids_avec_quantite_nulle_est_ignoree(tenant, donnees_poids):
    from laboutik.views import _extraire_articles_du_panier

    donnees_post = _panier_au_poids(
        donnees_poids["comte"], donnees_poids["tarif_comte"], 0, 700
    )
    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_poids["pv"])

    assert articles == []


def test_33_centilitres_a_8_euros_le_litre_coutent_264_centimes(tenant, donnees_poids):
    """
    Stock en centilitres : on divise par 100 (cl → L), pas par 1000.
    / Stock in centilitres: divide by 100 (cl → L), not 1000.
    """
    from laboutik.views import _extraire_articles_du_panier

    donnees_post = _panier_au_poids(
        donnees_poids["vin"], donnees_poids["tarif_vin"], 33, 264
    )
    with tenant_context(tenant):
        articles = _extraire_articles_du_panier(donnees_post, donnees_poids["pv"])

    assert len(articles) == 1
    assert articles[0]["prix_centimes"] == 264


def test_arrondi_au_centime_le_plus_proche(tenant, donnees_poids):
    """
    125 g a 20 €/kg = 250 centimes pile ; 333 g = 666 centimes ;
    1 g a 12,34 €/kg = 1,234 centime → 1 centime.
    / Rounding to the nearest cent.
    """
    from BaseBillet.models import Price
    from laboutik.views import _montant_poids_mesure_en_centimes

    comte = donnees_poids["comte"]
    with tenant_context(tenant):
        tarif_comte = donnees_poids["tarif_comte"]
        assert _montant_poids_mesure_en_centimes(comte, tarif_comte, 125) == 250
        assert _montant_poids_mesure_en_centimes(comte, tarif_comte, 333) == 666

        tarif_a_12_34 = Price(product=comte, prix=Decimal("12.34"), poids_mesure=True)
        assert _montant_poids_mesure_en_centimes(comte, tarif_a_12_34, 1) == 1
        assert _montant_poids_mesure_en_centimes(comte, tarif_a_12_34, 1000) == 1234
