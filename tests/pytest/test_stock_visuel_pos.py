"""
tests/pytest/test_stock_visuel_pos.py — Tests unitaires et integration pour
le helper _formater_stock_lisible() et l'enrichissement stock dans _construire_donnees_articles().
/ Unit and integration tests for the _formater_stock_lisible() helper
and stock enrichment in _construire_donnees_articles().

LOCALISATION : tests/pytest/test_stock_visuel_pos.py

Couvre :
  - _formater_stock_lisible : 10 cas (UN, CL, GR avec conversions et cas limites)
  - _construire_donnees_articles : 3 cas integration (sans stock, alerte, rupture bloquante)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_visuel_pos.py -v --api-key dummy
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")


import django

django.setup()

import pytest
from decimal import Decimal

from django_tenants.utils import schema_context

from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = "[test_stock_visuel]"

# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = "lespass"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in the database)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime toutes les donnees creees par ce module APRES execution.
    Ordre FK : Stock → PointDeVente → Price → Product.
    / Deletes all data created by this module AFTER execution. FK order respected.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import (
            Product,
            Price,
            LigneArticle,
            PriceSold,
            ProductSold,
        )
        from laboutik.models import PointDeVente
        from inventaire.models import Stock, MouvementStock

        # Supprimer les mouvements de stock lies aux produits de test
        # / Delete stock movements linked to test products
        MouvementStock.objects.filter(
            stock__product__name__startswith=TEST_PREFIX
        ).delete()

        # Supprimer les lignes articles liees aux produits de test
        # / Delete article lines linked to test products
        LigneArticle.objects.filter(
            pricesold__productsold__product__name__startswith=TEST_PREFIX
        ).delete()

        # Supprimer PriceSold et ProductSold
        # / Delete PriceSold and ProductSold
        PriceSold.objects.filter(
            productsold__product__name__startswith=TEST_PREFIX
        ).delete()
        ProductSold.objects.filter(product__name__startswith=TEST_PREFIX).delete()

        # Supprimer les stocks lies aux produits de test
        # / Delete stocks linked to test products
        Stock.objects.filter(product__name__startswith=TEST_PREFIX).delete()

        # Vider les M2M avant suppression des PointDeVente
        # / Clear M2M before deleting PointDeVente
        pdv_tests = PointDeVente.objects.filter(name__startswith=TEST_PREFIX)
        for pdv in pdv_tests:
            pdv.products.clear()
            pdv.categories.clear()
        pdv_tests.delete()

        Price.objects.filter(name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()


# ---------------------------------------------------------------------------
# Fonctions utilitaires pour les tests
# / Utility functions for tests
# ---------------------------------------------------------------------------


def creer_pdv_avec_produit(nom_prefix, product):
    """
    Cree un PointDeVente minimal et y ajoute le produit donne.
    Retourne le PDV cree.
    / Creates a minimal PointDeVente and adds the given product.
    Returns the created POS.
    """
    from laboutik.models import PointDeVente

    pdv = PointDeVente.objects.create(
        name=f"{TEST_PREFIX} PDV {nom_prefix}",
        comportement=PointDeVente.DIRECT,
    )
    pdv.products.add(product)
    return pdv


# ===========================================================================
# PARTIE 1 : Tests unitaires de _formater_stock_lisible()
# / PART 1: Unit tests for _formater_stock_lisible()
# ===========================================================================


def test_formater_un_normal():
    """UN : quantite positive affiche le nombre brut.
    / UN: positive quantity shows raw number."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(3, "UN") == "3"


def test_formater_un_zero():
    """UN : quantite zero affiche '0'.
    / UN: zero quantity shows '0'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(0, "UN") == "0"


def test_formater_un_negatif():
    """UN : quantite negative affiche le nombre negatif.
    / UN: negative quantity shows negative number."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(-2, "UN") == "-2"


def test_formater_cl_conversion_litres():
    """CL : 150 cl → '1.5 L'.
    / CL: 150 cl → '1.5 L'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(150, "CL") == "1.5 L"


def test_formater_cl_sous_cent():
    """CL : 50 cl reste en cl → '50 cl'.
    / CL: 50 cl stays in cl → '50 cl'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(50, "CL") == "50 cl"


def test_formater_cl_exact_litre():
    """CL : 100 cl → '1 L' (pas de decimale si entier).
    / CL: 100 cl → '1 L' (no decimal if whole)."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(100, "CL") == "1 L"


def test_formater_cl_zero():
    """CL : 0 cl → '0 cl'.
    / CL: 0 cl → '0 cl'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(0, "CL") == "0 cl"


def test_formater_gr_conversion_kg():
    """GR : 1200 g → '1.2 kg'.
    / GR: 1200 g → '1.2 kg'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(1200, "GR") == "1.2 kg"


def test_formater_gr_sous_mille():
    """GR : 800 g reste en g → '800 g'.
    / GR: 800 g stays in g → '800 g'."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(800, "GR") == "800 g"


def test_formater_gr_exact_kg():
    """GR : 1000 g → '1 kg' (pas de decimale si entier).
    / GR: 1000 g → '1 kg' (no decimal if whole)."""
    from laboutik.views import _formater_stock_lisible

    assert _formater_stock_lisible(1000, "GR") == "1 kg"


# ===========================================================================
# PARTIE 2 : Tests integration de _construire_donnees_articles() avec stock
# / PART 2: Integration tests for _construire_donnees_articles() with stock
# ===========================================================================


def test_article_sans_stock(tenant):
    """
    Un produit sans Stock lie doit avoir stock_quantite=None.
    / A product without linked Stock must have stock_quantite=None.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from laboutik.views import _construire_donnees_articles

        product = Product.objects.create(
            name=f"{TEST_PREFIX} Sans Stock",
            methode_caisse=Product.VENTE,
        )
        Price.objects.create(
            product=product,
            name=f"{TEST_PREFIX} Tarif Sans Stock",
            prix=Decimal("3.00"),
        )

        pdv = creer_pdv_avec_produit("Sans Stock", product)
        articles = _construire_donnees_articles(pdv)

        article = next(
            (a for a in articles if a["name"] == f"{TEST_PREFIX} Sans Stock"),
            None,
        )
        assert article is not None, "L'article doit etre dans la liste"
        assert article["stock_quantite"] is None, (
            "stock_quantite doit etre None quand pas de Stock lie"
        )


def test_article_stock_en_alerte(tenant):
    """
    Un produit avec stock sous le seuil d'alerte (mais > 0)
    doit avoir stock_en_alerte=True et stock_en_rupture=False.
    / A product with stock below alert threshold (but > 0)
    must have stock_en_alerte=True and stock_en_rupture=False.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from inventaire.models import Stock
        from laboutik.views import _construire_donnees_articles

        product = Product.objects.create(
            name=f"{TEST_PREFIX} Stock Alerte",
            methode_caisse=Product.VENTE,
        )
        Price.objects.create(
            product=product,
            name=f"{TEST_PREFIX} Tarif Alerte",
            prix=Decimal("4.00"),
        )
        Stock.objects.create(
            product=product,
            quantite=2,
            unite="UN",
            seuil_alerte=5,
            autoriser_vente_hors_stock=True,
        )

        pdv = creer_pdv_avec_produit("Stock Alerte", product)
        articles = _construire_donnees_articles(pdv)

        article = next(
            (a for a in articles if a["name"] == f"{TEST_PREFIX} Stock Alerte"),
            None,
        )
        assert article is not None, "L'article doit etre dans la liste"
        assert article["stock_quantite"] == 2
        assert article["stock_unite"] == "UN"
        assert article["stock_en_alerte"] is True, "stock sous seuil_alerte"
        assert article["stock_en_rupture"] is False, "stock > 0"
        assert article["stock_bloquant"] is False
        assert article["stock_quantite_lisible"] == "2"


def test_article_stock_rupture_bloquante(tenant):
    """
    Un produit a 0 avec autoriser_vente_hors_stock=False
    doit avoir stock_bloquant=True.
    / A product at 0 with autoriser_vente_hors_stock=False
    must have stock_bloquant=True.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from inventaire.models import Stock
        from laboutik.views import _construire_donnees_articles

        product = Product.objects.create(
            name=f"{TEST_PREFIX} Rupture Bloquante",
            methode_caisse=Product.VENTE,
        )
        Price.objects.create(
            product=product,
            name=f"{TEST_PREFIX} Tarif Rupture",
            prix=Decimal("6.00"),
        )
        Stock.objects.create(
            product=product,
            quantite=0,
            unite="CL",
            seuil_alerte=10,
            autoriser_vente_hors_stock=False,
        )

        pdv = creer_pdv_avec_produit("Rupture Bloquante", product)
        articles = _construire_donnees_articles(pdv)

        article = next(
            (a for a in articles if a["name"] == f"{TEST_PREFIX} Rupture Bloquante"),
            None,
        )
        assert article is not None, "L'article doit etre dans la liste"
        assert article["stock_quantite"] == 0
        assert article["stock_unite"] == "CL"
        assert article["stock_en_rupture"] is True, "stock = 0"
        assert article["stock_bloquant"] is True, "vente hors stock interdite"
        assert article["stock_quantite_lisible"] == "0 cl"


# ===========================================================================
# PARTIE 3 : Test broadcast WebSocket apres decrementation stock
# / PART 3: WebSocket broadcast test after stock decrement
# ===========================================================================


def test_broadcast_stock_appele_apres_decrementation(tenant):
    """
    Apres une vente d'un produit avec stock, broadcast_stock_update()
    est enregistre via on_commit() avec les donnees stock a jour.
    / After selling a product with stock, broadcast_stock_update()
    is registered via on_commit() with updated stock data.
    """
    from unittest.mock import patch

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from inventaire.models import Stock
        from laboutik.models import PointDeVente
        from laboutik.views import _creer_lignes_articles

        product = Product.objects.create(
            name=f"{TEST_PREFIX} Soda Broadcast",
            methode_caisse=Product.VENTE,
            publish=True,
        )
        price = Price.objects.create(
            product=product,
            name=f"{TEST_PREFIX} Tarif Broadcast",
            prix=Decimal("3.00"),
            publish=True,
        )
        Stock.objects.create(
            product=product,
            quantite=10,
            unite="UN",
            seuil_alerte=3,
        )
        pv = PointDeVente.objects.create(
            name=f"{TEST_PREFIX} PV Broadcast",
            comportement=PointDeVente.DIRECT,
        )

        articles_panier = [
            {
                "product": product,
                "price": price,
                "quantite": 1,
                "prix_centimes": 300,
            }
        ]

        with patch("wsocket.broadcast.broadcast_stock_update") as mock_broadcast:
            _creer_lignes_articles(
                articles_panier,
                "espece",
                point_de_vente=pv,
            )
            # on_commit() n'est pas execute en test car pas de vrai commit.
            # On verifie que la fonction est appelee directement
            # si on est hors transaction.atomic() (mode autocommit du test).
            # / on_commit() fires immediately in autocommit mode (test default).
            mock_broadcast.assert_called_once()
            donnees = mock_broadcast.call_args[0][0]
            assert len(donnees) == 1
            assert donnees[0]["product_uuid"] == str(product.uuid)
            assert donnees[0]["quantite"] == 9
            assert donnees[0]["en_alerte"] is False
            assert donnees[0]["en_rupture"] is False
