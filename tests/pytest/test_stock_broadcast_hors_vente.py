"""
tests/pytest/test_stock_broadcast_hors_vente.py
Les caisses sont prévenues quand le stock change HORS vente (admin, panel, API).
/ POS terminals are notified when stock changes OUTSIDE a sale (admin, panel, API).

Bug d'origine : une réception faite depuis l'admin ne changeait rien sur les
caisses ouvertes. Seules les ventes envoyaient le badge stock par WebSocket.
/ Original bug: a reception done from the admin did not update open POS terminals.

Couvre / Covers:
- StockService.creer_mouvement → broadcast du badge à jour
- StockService.ajuster_inventaire → broadcast du badge à jour
- StockAdmin.save_model (modification) → broadcast (ex : vente hors stock bloquée)
- StockAdmin.save_model (création) → la quantité saisie n'est pas doublée

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_broadcast_hors_vente.py -v

LOCALISATION : tests/pytest/test_stock_broadcast_hors_vente.py
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")


import django

django.setup()

from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django_tenants.utils import schema_context

from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = "[test_stock_broadcast_hors_vente]"

# Schema tenant utilise pour les tests (autocommit : on_commit s'execute tout de suite).
# / Tenant schema used for tests (autocommit: on_commit runs immediately).
TENANT_SCHEMA = "lespass"


@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in the database)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime les donnees de ce module APRES execution.
    Ordre FK : MouvementStock → Stock → Product.
    / Deletes this module's data AFTER execution. FK order respected.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product
        from inventaire.models import MouvementStock, Stock

        MouvementStock.objects.filter(
            stock__product__name__startswith=TEST_PREFIX
        ).delete()
        Stock.objects.filter(product__name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()


def _creer_produit_avec_stock(nom, quantite, autoriser_vente_hors_stock=False):
    """Cree un produit de vente et son Stock en pieces.
    / Creates a sale product and its Stock in units."""
    from BaseBillet.models import Product
    from inventaire.models import Stock

    produit = Product.objects.create(
        name=f"{TEST_PREFIX} {nom}",
        methode_caisse=Product.VENTE,
        publish=True,
    )
    stock = Stock.objects.create(
        product=produit,
        quantite=quantite,
        unite="UN",
        autoriser_vente_hors_stock=autoriser_vente_hors_stock,
    )
    return produit, stock


def _utilisateur_admin_de_test():
    """Un utilisateur pour request.user (cree_par des mouvements).
    / A user for request.user (movement cree_par)."""
    from AuthBillet.models import TibilletUser

    utilisateur, _created = TibilletUser.objects.get_or_create(
        email="admin-stock-broadcast@tibillet.localhost",
        defaults={
            "username": "admin-stock-broadcast@tibillet.localhost",
            "is_staff": True,
            "is_active": True,
        },
    )
    return utilisateur


def test_reception_previent_les_caisses_avec_le_stock_a_jour(tenant):
    """Une reception de +5 sur un stock a 0 envoie le badge : plus en rupture, plus bloquant.
    / A +5 reception on a zero stock sends the badge: no longer out of stock or blocking."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import TypeMouvement
        from inventaire.services import StockService

        produit, stock = _creer_produit_avec_stock("Biere reception", quantite=0)

        with patch("wsocket.broadcast.broadcast_stock_update") as mock_broadcast:
            StockService.creer_mouvement(
                stock=stock,
                type_mouvement=TypeMouvement.RE,
                quantite=5,
            )

        mock_broadcast.assert_called_once()
        donnees = mock_broadcast.call_args[0][0]
        assert len(donnees) == 1
        assert donnees[0]["product_uuid"] == str(produit.uuid)
        assert donnees[0]["quantite"] == 5
        assert donnees[0]["en_rupture"] is False
        assert donnees[0]["bloquant"] is False


def test_ajustement_inventaire_previent_les_caisses(tenant):
    """Un ajustement a 0 d'un stock bloquant envoie un badge bloquant.
    / An adjustment to 0 on a blocking stock sends a blocking badge."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.services import StockService

        produit, stock = _creer_produit_avec_stock("Biere ajustement", quantite=8)

        with patch("wsocket.broadcast.broadcast_stock_update") as mock_broadcast:
            StockService.ajuster_inventaire(stock=stock, stock_reel=0)

        mock_broadcast.assert_called_once()
        donnees = mock_broadcast.call_args[0][0]
        assert donnees[0]["product_uuid"] == str(produit.uuid)
        assert donnees[0]["quantite"] == 0
        assert donnees[0]["en_rupture"] is True
        assert donnees[0]["bloquant"] is True


def test_modification_de_la_fiche_stock_dans_l_admin_previent_les_caisses(tenant):
    """Autoriser la vente hors stock depuis l'admin debloque la tuile sur les caisses.
    / Allowing out-of-stock sales from the admin unblocks the tile on POS terminals."""
    with schema_context(TENANT_SCHEMA):
        from Administration.admin.inventaire import StockAdmin
        from Administration.admin.site import staff_admin_site
        from inventaire.models import Stock

        produit, stock = _creer_produit_avec_stock("Biere admin modif", quantite=0)

        requete = RequestFactory().post("/")
        requete.user = _utilisateur_admin_de_test()
        stock.autoriser_vente_hors_stock = True

        with patch("wsocket.broadcast.broadcast_stock_update") as mock_broadcast:
            StockAdmin(Stock, staff_admin_site).save_model(
                requete, stock, form=None, change=True
            )

        mock_broadcast.assert_called_once()
        donnees = mock_broadcast.call_args[0][0]
        assert donnees[0]["product_uuid"] == str(produit.uuid)
        assert donnees[0]["en_rupture"] is True
        assert donnees[0]["bloquant"] is False


def test_creation_du_stock_dans_l_admin_ne_double_pas_la_quantite(tenant):
    """Creer un stock de 10 dans l'admin donne 10, pas 20.
    Le mouvement "Stock initial" part de 0.
    / Creating a stock of 10 in the admin gives 10, not 20."""
    with schema_context(TENANT_SCHEMA):
        from Administration.admin.inventaire import StockAdmin
        from Administration.admin.site import staff_admin_site
        from BaseBillet.models import Product
        from inventaire.models import MouvementStock, Stock

        produit = Product.objects.create(
            name=f"{TEST_PREFIX} Biere admin creation",
            methode_caisse=Product.VENTE,
            publish=True,
        )
        nouveau_stock = Stock(product=produit, quantite=10, unite="UN")

        requete = RequestFactory().post("/")
        requete.user = _utilisateur_admin_de_test()

        with patch("wsocket.broadcast.broadcast_stock_update"):
            StockAdmin(Stock, staff_admin_site).save_model(
                requete, nouveau_stock, form=None, change=False
            )

        nouveau_stock.refresh_from_db()
        assert nouveau_stock.quantite == 10

        mouvement_initial = MouvementStock.objects.get(stock=nouveau_stock)
        assert mouvement_initial.quantite == 10
        assert mouvement_initial.quantite_avant == 0
