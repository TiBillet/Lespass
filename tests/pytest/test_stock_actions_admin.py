"""
tests/pytest/test_stock_actions_admin.py — Tests pour la vue stock_action_view.
Couvre les 4 types manuels (réception, ajustement, offert, perte) + rejet type invalide.
/ Tests for the stock_action_view. Covers 4 manual types + invalid type rejection.

LOCALISATION : tests/pytest/test_stock_actions_admin.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_stock_actions_admin.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from decimal import Decimal
from unittest.mock import patch

from django.test import RequestFactory
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = "[test_stock_action]"

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


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin pour les requêtes.
    / An admin user for requests."""
    with schema_context(TENANT_SCHEMA):
        email = "admin-test-stock-action@tibillet.localhost"
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "is_staff": True,
                "is_active": True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime toutes les donnees creees par ce module APRES execution.
    / Deletes all data created by this module AFTER execution.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import Product, Price
        from inventaire.models import Stock, MouvementStock

        MouvementStock.objects.filter(
            stock__product__name__startswith=TEST_PREFIX
        ).delete()
        Stock.objects.filter(product__name__startswith=TEST_PREFIX).delete()
        Price.objects.filter(product__name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()


# ---------------------------------------------------------------------------
# Fonction utilitaire pour creer un produit avec stock
# / Utility function to create a product with stock
# ---------------------------------------------------------------------------


def creer_produit_avec_stock(suffixe, quantite_initiale=20):
    """
    Cree un Product + Price + Stock avec la quantite donnee.
    / Creates a Product + Price + Stock with the given quantity.
    """
    from BaseBillet.models import Product, Price
    from inventaire.models import Stock

    product = Product.objects.create(
        name=f"{TEST_PREFIX} {suffixe}",
        methode_caisse=Product.VENTE,
    )
    Price.objects.create(
        product=product,
        name=f"{TEST_PREFIX} prix {suffixe}",
        prix=Decimal("3.00"),
    )
    stock = Stock.objects.create(
        product=product,
        quantite=quantite_initiale,
        unite="UN",
    )
    return product, stock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reception_augmente_stock(tenant, admin_user):
    """Réception de 5 unités : stock passe de 20 à 25.
    / Reception of 5 units: stock goes from 20 to 25."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import MouvementStock
        from inventaire.views import stock_action_view

        product, stock = creer_produit_avec_stock("Reception")

        factory = RequestFactory()
        request = factory.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "RE",
                "quantite": "5",
                "motif": "Livraison test",
            },
        )
        request.user = admin_user

        with patch("inventaire.views.render_to_string", return_value="<div>ok</div>"):
            response = stock_action_view(request, str(stock.pk))

        assert response.status_code == 200

        stock.refresh_from_db()
        assert stock.quantite == 25

        dernier_mouvement = MouvementStock.objects.filter(stock=stock).first()
        assert dernier_mouvement is not None
        assert dernier_mouvement.type_mouvement == "RE"
        assert dernier_mouvement.quantite == 5


def test_ajustement_remplace_stock(tenant, admin_user):
    """Ajustement à 12 : stock passe de 20 à 12.
    / Adjustment to 12: stock goes from 20 to 12."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import MouvementStock
        from inventaire.views import stock_action_view

        product, stock = creer_produit_avec_stock("Ajustement")

        factory = RequestFactory()
        request = factory.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "AJ",
                "quantite": "12",
                "motif": "Inventaire compté",
            },
        )
        request.user = admin_user

        with patch("inventaire.views.render_to_string", return_value="<div>ok</div>"):
            response = stock_action_view(request, str(stock.pk))

        assert response.status_code == 200

        stock.refresh_from_db()
        assert stock.quantite == 12

        dernier_mouvement = MouvementStock.objects.filter(stock=stock).first()
        assert dernier_mouvement is not None
        assert dernier_mouvement.type_mouvement == "AJ"
        # Delta = 12 - 20 = -8
        assert dernier_mouvement.quantite == -8


def test_perte_diminue_stock(tenant, admin_user):
    """Perte de 3 : stock passe de 20 à 17.
    / Loss of 3: stock goes from 20 to 17."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import MouvementStock
        from inventaire.views import stock_action_view

        product, stock = creer_produit_avec_stock("Perte")

        factory = RequestFactory()
        request = factory.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "PE",
                "quantite": "3",
                "motif": "Casse",
            },
        )
        request.user = admin_user

        with patch("inventaire.views.render_to_string", return_value="<div>ok</div>"):
            response = stock_action_view(request, str(stock.pk))

        assert response.status_code == 200

        stock.refresh_from_db()
        assert stock.quantite == 17

        dernier_mouvement = MouvementStock.objects.filter(stock=stock).first()
        assert dernier_mouvement is not None
        assert dernier_mouvement.type_mouvement == "PE"
        # Delta negatif pour perte
        assert dernier_mouvement.quantite == -3


def test_offert_diminue_stock(tenant, admin_user):
    """Offert de 2 : stock passe de 20 à 18.
    / Offered 2: stock goes from 20 to 18."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import MouvementStock
        from inventaire.views import stock_action_view

        product, stock = creer_produit_avec_stock("Offert")

        factory = RequestFactory()
        request = factory.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "OF",
                "quantite": "2",
                "motif": "Cadeau client",
            },
        )
        request.user = admin_user

        with patch("inventaire.views.render_to_string", return_value="<div>ok</div>"):
            response = stock_action_view(request, str(stock.pk))

        assert response.status_code == 200

        stock.refresh_from_db()
        assert stock.quantite == 18

        dernier_mouvement = MouvementStock.objects.filter(stock=stock).first()
        assert dernier_mouvement is not None
        assert dernier_mouvement.type_mouvement == "OF"
        assert dernier_mouvement.quantite == -2


def test_type_invalide_ve_rejete(tenant, admin_user):
    """Le type VE (vente) est rejeté par le serializer.
    / VE (sale) type is rejected by the serializer."""
    with schema_context(TENANT_SCHEMA):
        from inventaire.models import MouvementStock
        from inventaire.views import stock_action_view

        product, stock = creer_produit_avec_stock("TypeInvalide")

        factory = RequestFactory()
        request = factory.post(
            f"/admin/inventaire/stock/{stock.pk}/action/",
            data={
                "type_mouvement": "VE",
                "quantite": "5",
            },
        )
        request.user = admin_user

        with patch("inventaire.views.render_to_string", return_value="<div>ok</div>"):
            response = stock_action_view(request, str(stock.pk))

        assert response.status_code == 200

        # Le stock ne doit pas avoir changé
        # / Stock must not have changed
        stock.refresh_from_db()
        assert stock.quantite == 20

        # Aucun mouvement ne doit avoir été créé
        # / No movement should have been created
        nb_mouvements = MouvementStock.objects.filter(stock=stock).count()
        assert nb_mouvements == 0
