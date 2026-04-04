"""
Tests pour le panel contextuel article POS (long press).
/ Tests for the POS article context panel (long press).

LOCALISATION : tests/pytest/test_longpress_panel.py

Couvre :
- GET panel (menu principal)
- GET stock detail
- POST stock action (reception, offert, perte)
- Validation (quantite invalide, action invalide)
- Produit sans stock

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_longpress_panel.py -v
"""

import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import uuid as uuid_module
from unittest.mock import patch

import pytest
from django.db import connection
from django.test import RequestFactory
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from AuthBillet.models import TibilletUser
from Customers.models import Client


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = "[test_longpress_panel]"

# Schema tenant utilise pour les tests (doit exister dans la base dev).
# / Tenant schema used for tests (must exist in dev database).
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
    """Un utilisateur admin du tenant pour les requetes authentifiees.
    / A tenant admin user for authenticated requests."""
    with schema_context(TENANT_SCHEMA):
        email = "admin-longpress-panel-test@tibillet.localhost"
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "is_staff": True,
                "is_active": True,
            },
        )
        # Ajouter au tenant pour que is_tenant_admin() retourne True.
        # / Add to tenant so is_tenant_admin() returns True.
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
        from BaseBillet.models import Product
        from inventaire.models import Stock, MouvementStock

        MouvementStock.objects.filter(
            stock__product__name__startswith=TEST_PREFIX
        ).delete()
        Stock.objects.filter(product__name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()


@pytest.fixture
def factory():
    """RequestFactory Django."""
    return RequestFactory()


# ---------------------------------------------------------------------------
# Fonctions utilitaires
# / Utility functions
# ---------------------------------------------------------------------------


def creer_produit_avec_stock(
    suffixe, quantite_initiale=500, unite="CL", seuil_alerte=200
):
    """
    Cree un Product avec un Stock associe.
    / Creates a Product with an associated Stock.
    """
    from BaseBillet.models import Product
    from inventaire.models import Stock

    product = Product.objects.create(
        name=f"{TEST_PREFIX} {suffixe}",
        publish=True,
    )
    stock = Stock.objects.create(
        product=product,
        quantite=quantite_initiale,
        unite=unite,
        seuil_alerte=seuil_alerte,
    )
    return product, stock


def creer_produit_sans_stock(suffixe):
    """
    Cree un Product sans Stock.
    / Creates a Product without Stock.
    """
    from BaseBillet.models import Product

    product = Product.objects.create(
        name=f"{TEST_PREFIX} {suffixe}",
        publish=True,
    )
    return product


# ---------------------------------------------------------------------------
# Tests GET panel/ — menu principal
# ---------------------------------------------------------------------------


class TestArticlePanelMenu:
    """Tests pour le menu principal du panel contextuel (GET panel/).
    / Tests for the context panel main menu (GET panel/)."""

    def test_panel_avec_stock(self, factory, admin_user, tenant):
        """Le menu affiche le bouton Stock actif si le produit a un stock.
        / Menu shows active Stock button if product has a stock."""
        with schema_context(TENANT_SCHEMA):
            connection.set_tenant(tenant)

            from laboutik.views import ArticlePanelViewSet

            product, stock = creer_produit_avec_stock("Panel Avec Stock")

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="panel-btn-stock"' in content
            assert "hx-get" in content

    def test_panel_sans_stock(self, factory, admin_user, tenant):
        """Le menu affiche le bouton Stock desactive si pas de stock.
        / Menu shows disabled Stock button if no stock."""
        with schema_context(TENANT_SCHEMA):
            connection.set_tenant(tenant)

            from laboutik.views import ArticlePanelViewSet

            product = creer_produit_sans_stock("Panel Sans Stock")

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="panel-btn-stock-disabled"' in content

    def test_panel_produit_inexistant(self, factory, admin_user, tenant):
        """404 si le produit n'existe pas.
        / 404 if the product does not exist."""
        with schema_context(TENANT_SCHEMA):
            connection.set_tenant(tenant)

            from laboutik.views import ArticlePanelViewSet

            view = ArticlePanelViewSet.as_view({"get": "panel"})
            fake_uuid = uuid_module.uuid4()
            request = factory.get(f"/laboutik/article-panel/{fake_uuid}/panel/")
            request.user = admin_user

            response = view(request, product_uuid=fake_uuid)
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests GET stock/ — vue stock detaillee
# ---------------------------------------------------------------------------


class TestArticlePanelStock:
    """Tests pour la vue stock detaillee (GET stock/).
    / Tests for the detailed stock view (GET stock/)."""

    def test_stock_detail(self, factory, admin_user, tenant):
        """La vue stock affiche la quantite et les boutons d'action.
        / Stock view shows quantity and action buttons."""
        with schema_context(TENANT_SCHEMA):
            connection.set_tenant(tenant)

            from laboutik.views import ArticlePanelViewSet

            # 500 cl = 5 L
            product, stock = creer_produit_avec_stock(
                "Stock Detail", quantite_initiale=500, unite="CL"
            )

            view = ArticlePanelViewSet.as_view({"get": "stock_detail"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/stock/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)

            assert response.status_code == 200
            content = response.content.decode()
            # 500 cl = 5 L
            assert "5 L" in content
            assert 'data-testid="stock-btn-reception"' in content
            assert 'data-testid="stock-btn-perte"' in content
            assert 'data-testid="stock-btn-ajustement"' in content

    def test_stock_detail_sans_stock(self, factory, admin_user, tenant):
        """404 si le produit n'a pas de stock.
        / 404 if the product has no stock."""
        with schema_context(TENANT_SCHEMA):
            connection.set_tenant(tenant)

            from laboutik.views import ArticlePanelViewSet

            product = creer_produit_sans_stock("Stock Detail Sans Stock")

            view = ArticlePanelViewSet.as_view({"get": "stock_detail"})
            request = factory.get(f"/laboutik/article-panel/{product.uuid}/stock/")
            request.user = admin_user

            response = view(request, product_uuid=product.uuid)
            assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests POST stock/{action}/ — actions stock
# ---------------------------------------------------------------------------


class TestArticlePanelStockActions:
    """Tests pour les actions stock (POST stock/{action}/).
    Utilise APIClient + force_authenticate pour eviter le CSRF de DRF SessionAuthentication.
    / Tests for stock actions (POST stock/{action}/).
    Uses APIClient + force_authenticate to bypass DRF SessionAuthentication CSRF."""

    def _make_client(self, admin_user):
        """Cree un client DRF authentifie comme admin du tenant.
        / Creates a DRF client authenticated as tenant admin."""
        client = APIClient()
        client.force_authenticate(user=admin_user)
        client.defaults["SERVER_NAME"] = f"{TENANT_SCHEMA}.tibillet.localhost"
        return client

    def test_reception(self, admin_user, tenant):
        """POST reception ajoute du stock et retourne la vue mise a jour.
        / POST reception adds stock and returns updated view."""
        with schema_context(TENANT_SCHEMA):
            product, stock = creer_produit_avec_stock(
                "Reception", quantite_initiale=500, unite="CL"
            )

            client = self._make_client(admin_user)
            with patch("laboutik.views.broadcast_stock_update"):
                response = client.post(
                    f"/laboutik/article-panel/{product.uuid}/stock/reception/",
                    data={"quantite": "100", "motif": "Livraison test"},
                )

            assert response.status_code == 200
            assert response.get("HX-Trigger") == "stockUpdated"

            stock.refresh_from_db()
            # 500 + 100 = 600 cl
            assert stock.quantite == 600

    def test_perte(self, admin_user, tenant):
        """POST perte retire du stock.
        / POST perte removes stock."""
        with schema_context(TENANT_SCHEMA):
            product, stock = creer_produit_avec_stock(
                "Perte", quantite_initiale=500, unite="CL"
            )

            client = self._make_client(admin_user)
            with patch("laboutik.views.broadcast_stock_update"):
                response = client.post(
                    f"/laboutik/article-panel/{product.uuid}/stock/perte/",
                    data={"quantite": "50", "motif": "Casse"},
                )

            assert response.status_code == 200
            stock.refresh_from_db()
            # 500 - 50 = 450 cl
            assert stock.quantite == 450

    def test_ajustement(self, admin_user, tenant):
        """POST ajustement remplace le stock par la valeur saisie.
        / POST ajustement replaces stock with entered value."""
        with schema_context(TENANT_SCHEMA):
            product, stock = creer_produit_avec_stock(
                "Ajustement", quantite_initiale=500, unite="CL"
            )

            client = self._make_client(admin_user)
            with patch("laboutik.views.broadcast_stock_update"):
                response = client.post(
                    f"/laboutik/article-panel/{product.uuid}/stock/ajustement/",
                    data={"quantite": "200", "motif": "Inventaire physique"},
                )

            assert response.status_code == 200
            assert response.get("HX-Trigger") == "stockUpdated"
            stock.refresh_from_db()
            # Ajustement : stock_reel=200 (remplace 500)
            assert stock.quantite == 200

    def test_action_invalide(self, admin_user, tenant):
        """Une action non autorisee retourne 400.
        / An unauthorized action returns 400."""
        with schema_context(TENANT_SCHEMA):
            product, stock = creer_produit_avec_stock("Action Invalide")

            client = self._make_client(admin_user)
            response = client.post(
                f"/laboutik/article-panel/{product.uuid}/stock/offert/",
                data={"quantite": "10"},
            )
            assert response.status_code == 400

    def test_quantite_invalide(self, admin_user, tenant):
        """Quantite 0 ou negative retourne le formulaire avec erreur.
        / Quantity 0 or negative returns form with error."""
        with schema_context(TENANT_SCHEMA):
            product, stock = creer_produit_avec_stock(
                "Quantite Invalide", quantite_initiale=500
            )

            client = self._make_client(admin_user)
            response = client.post(
                f"/laboutik/article-panel/{product.uuid}/stock/reception/",
                data={"quantite": "0"},
            )

            assert response.status_code == 200
            content = response.content.decode()
            assert 'data-testid="stock-feedback-error"' in content
            # Stock inchange / Stock unchanged
            stock.refresh_from_db()
            assert stock.quantite == 500
