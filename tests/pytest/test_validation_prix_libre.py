"""
tests/pytest/test_validation_prix_libre.py — Tests de la validation serveur du prix libre.
/ Server-side free price validation tests.

LOCALISATION : tests/pytest/test_validation_prix_libre.py

Couvre :
  - _extraire_articles_du_panier : rejet montant sous le minimum (ValueError)
  - _extraire_articles_du_panier : montant valide (>= minimum) accepté
  - _extraire_articles_du_panier : custom_amount ignoré si free_price=False
  - PanierSerializer.extraire_articles_du_post : extraction correcte du custom_amount
  - PaiementViewSet.moyens_paiement : HTTP 400 si montant libre invalide
  - PaiementViewSet.payer : HTTP 400 si montant libre invalide

Prerequis / Prerequisites:
  - Base de donnees avec le tenant 'lespass' existant
  - create_test_pos_data déjà lancé (ou lancé par la fixture test_data)

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_validation_prix_libre.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest
from decimal import Decimal

from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import Price, Product
from Customers.models import Client
from laboutik.models import PointDeVente
from laboutik.serializers import PanierSerializer


# Prefixe pour identifier les donnees de ce module et les nettoyer.
# / Prefix to identify this module's data and clean it up.
TEST_PREFIX = '[test_prix_libre]'

# Schema tenant utilise pour les tests.
# / Tenant schema used for tests.
TENANT_SCHEMA = 'lespass'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant():
    """Le tenant 'lespass' (doit exister dans la base).
    / The 'lespass' tenant (must exist in DB)."""
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def test_data(tenant):
    """Lance create_test_pos_data pour s'assurer que les donnees existent.
    / Runs create_test_pos_data to ensure test data exists."""
    from django.core.management import call_command
    call_command('create_test_pos_data')
    return True


@pytest.fixture(scope="module")
def admin_user(tenant):
    """Un utilisateur admin du tenant.
    / A tenant admin user."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-prix-libre@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        return user


@pytest.fixture(scope="module")
def pv_et_produits(test_data):
    """
    Crée un PV de test avec un produit à prix libre et un produit à prix fixe.
    / Creates a test PV with a free-price product and a fixed-price product.
    """
    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct

        # Catégorie de test
        # / Test category
        categorie, _ = CategorieProduct.objects.get_or_create(
            name=f"{TEST_PREFIX} Catégorie",
        )

        # Produit avec prix libre (minimum 5.00€)
        # / Product with free price (minimum 5.00€)
        produit_libre, _ = Product.objects.get_or_create(
            name=f"{TEST_PREFIX} Bière prix libre",
            defaults={
                'publish': True,
                'categorie_article': Product.BILLET,
                'methode_caisse': Product.VENTE,
                'categorie_pos': categorie,
            },
        )
        prix_libre, _ = Price.objects.get_or_create(
            product=produit_libre,
            name=f"{TEST_PREFIX} Prix libre",
            defaults={
                'prix': Decimal('5.00'),
                'free_price': True,
                'publish': True,
            },
        )

        # Produit avec prix fixe (pas de prix libre)
        # / Product with fixed price (not free price)
        produit_fixe, _ = Product.objects.get_or_create(
            name=f"{TEST_PREFIX} Bière classique",
            defaults={
                'publish': True,
                'categorie_article': Product.BILLET,
                'methode_caisse': Product.VENTE,
                'categorie_pos': categorie,
            },
        )
        prix_fixe, _ = Price.objects.get_or_create(
            product=produit_fixe,
            name=f"{TEST_PREFIX} Prix fixe",
            defaults={
                'prix': Decimal('3.50'),
                'free_price': False,
                'publish': True,
            },
        )

        # Point de vente de test
        # / Test point of sale
        pv, _ = PointDeVente.objects.get_or_create(
            name=f"{TEST_PREFIX} PV Test",
            defaults={
                'comportement': PointDeVente.DIRECT,
            },
        )
        pv.products.add(produit_libre, produit_fixe)

        return {
            'pv': pv,
            'produit_libre': produit_libre,
            'prix_libre': prix_libre,
            'produit_fixe': produit_fixe,
            'prix_fixe': prix_fixe,
        }


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data(tenant):
    """
    Supprime toutes les données créées par ce module APRÈS exécution.
    / Deletes all data created by this module AFTER execution. FK order respected.
    """
    yield

    with schema_context(TENANT_SCHEMA):
        from BaseBillet.models import CategorieProduct

        # Vider les M2M avant suppression des PointDeVente
        # / Clear M2M before deleting PointDeVente
        pdv_tests = PointDeVente.objects.filter(name__startswith=TEST_PREFIX)
        for pdv in pdv_tests:
            pdv.products.clear()
        pdv_tests.delete()

        Price.objects.filter(name__startswith=TEST_PREFIX).delete()
        Product.objects.filter(name__startswith=TEST_PREFIX).delete()
        CategorieProduct.objects.filter(name__startswith=TEST_PREFIX).delete()


def _make_client(admin_user, tenant):
    """Crée un client DRF authentifié comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


# ---------------------------------------------------------------------------
# Tests — PanierSerializer.extraire_articles_du_post
# ---------------------------------------------------------------------------

class TestPanierSerializerExtractionPrixLibre:
    """Tests d'extraction du prix libre depuis le POST.
    / Tests for free price extraction from POST data."""

    def test_extraction_custom_amount_avec_price_uuid(self, pv_et_produits):
        """Le montant custom est correctement extrait quand le price_uuid est fourni.
        / Custom amount is correctly extracted when price_uuid is provided."""
        with schema_context(TENANT_SCHEMA):
            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']

            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '750',
            }

            articles = PanierSerializer.extraire_articles_du_post(post_data)
            assert len(articles) == 1
            assert articles[0]['custom_amount_centimes'] == 750
            assert articles[0]['price_uuid'] == str(prix.uuid)

    def test_extraction_sans_custom_amount(self, pv_et_produits):
        """Sans champ custom, custom_amount_centimes est None.
        / Without custom field, custom_amount_centimes is None."""
        with schema_context(TENANT_SCHEMA):
            produit = pv_et_produits['produit_fixe']
            prix = pv_et_produits['prix_fixe']

            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
            }

            articles = PanierSerializer.extraire_articles_du_post(post_data)
            assert len(articles) == 1
            assert articles[0]['custom_amount_centimes'] is None

    def test_extraction_custom_amount_invalide_ignore(self, pv_et_produits):
        """Un montant custom non numérique est ignoré (custom_amount_centimes = None).
        / A non-numeric custom amount is ignored (custom_amount_centimes = None)."""
        with schema_context(TENANT_SCHEMA):
            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']

            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': 'abc',
            }

            articles = PanierSerializer.extraire_articles_du_post(post_data)
            assert len(articles) == 1
            assert articles[0]['custom_amount_centimes'] is None


# ---------------------------------------------------------------------------
# Tests — _extraire_articles_du_panier (validation serveur)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestValidationPrixLibreServeur:
    """Tests de la validation serveur du montant libre dans _extraire_articles_du_panier.
    / Tests for server-side free price validation in _extraire_articles_du_panier."""

    def test_montant_sous_minimum_leve_valueerror(self, pv_et_produits):
        """Un montant libre inférieur au minimum lève ValueError.
        / A free price amount below minimum raises ValueError."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']
            pv = pv_et_produits['pv']

            # Minimum = 5.00€ = 500 centimes. Envoyer 200 centimes (2.00€).
            # / Minimum = 5.00€ = 500 cents. Send 200 cents (2.00€).
            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '200',
            }

            with pytest.raises(ValueError) as exc_info:
                _extraire_articles_du_panier(post_data, pv)

            # Le message doit contenir les montants pour le debug
            # / The message should contain amounts for debugging
            message_erreur = str(exc_info.value)
            assert '2.00' in message_erreur
            assert '5.00' in message_erreur

    def test_montant_negatif_leve_valueerror(self, pv_et_produits):
        """Un montant libre négatif lève ValueError.
        / A negative free price amount raises ValueError."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']
            pv = pv_et_produits['pv']

            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '-500',
            }

            with pytest.raises(ValueError):
                _extraire_articles_du_panier(post_data, pv)

    def test_montant_egal_minimum_accepte(self, pv_et_produits):
        """Un montant libre égal au minimum est accepté.
        / A free price amount equal to minimum is accepted."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']
            pv = pv_et_produits['pv']

            # Minimum = 5.00€ = 500 centimes. Envoyer exactement 500.
            # / Minimum = 5.00€ = 500 cents. Send exactly 500.
            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '500',
            }

            articles = _extraire_articles_du_panier(post_data, pv)
            assert len(articles) == 1
            assert articles[0]['prix_centimes'] == 500
            assert articles[0]['custom_amount_centimes'] == 500

    def test_montant_superieur_minimum_accepte(self, pv_et_produits):
        """Un montant libre supérieur au minimum est accepté.
        / A free price amount above minimum is accepted."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']
            pv = pv_et_produits['pv']

            # Minimum = 5.00€. Envoyer 1000 centimes (10.00€).
            # / Minimum = 5.00€. Send 1000 cents (10.00€).
            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '1000',
            }

            articles = _extraire_articles_du_panier(post_data, pv)
            assert len(articles) == 1
            assert articles[0]['prix_centimes'] == 1000
            assert articles[0]['custom_amount_centimes'] == 1000

    def test_custom_amount_sur_prix_non_libre_ignore(self, pv_et_produits):
        """Un montant custom envoyé pour un prix non-libre est silencieusement ignoré.
        Le prix standard est utilisé à la place.
        / A custom amount sent for a non-free price is silently ignored.
        The standard price is used instead."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_fixe']
            prix = pv_et_produits['prix_fixe']
            pv = pv_et_produits['pv']

            # Le prix fixe est 3.50€. Tenter d'envoyer 100 centimes (1.00€).
            # / Fixed price is 3.50€. Try to send 100 cents (1.00€).
            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '100',
            }

            # Pas de ValueError — le custom est juste ignoré
            # / No ValueError — custom is just ignored
            articles = _extraire_articles_du_panier(post_data, pv)
            assert len(articles) == 1

            # Le prix utilisé est le prix standard (3.50€ = 350 centimes)
            # / The price used is the standard one (3.50€ = 350 cents)
            assert articles[0]['prix_centimes'] == 350
            assert articles[0]['custom_amount_centimes'] is None

    def test_sans_custom_amount_utilise_prix_standard(self, pv_et_produits):
        """Sans montant custom, le prix standard de la DB est utilisé.
        / Without custom amount, the standard DB price is used."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.views import _extraire_articles_du_panier

            produit = pv_et_produits['produit_fixe']
            prix = pv_et_produits['prix_fixe']
            pv = pv_et_produits['pv']

            post_data = {
                f'repid-{produit.uuid}--{prix.uuid}': '1',
            }

            articles = _extraire_articles_du_panier(post_data, pv)
            assert len(articles) == 1
            assert articles[0]['prix_centimes'] == 350
            assert articles[0]['custom_amount_centimes'] is None


# ---------------------------------------------------------------------------
# Tests — Vue HTTP (PaiementViewSet)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestVuePaiementPrixLibreInvalide:
    """Tests HTTP : les endpoints de paiement rejettent un montant libre invalide.
    / HTTP tests: payment endpoints reject an invalid free price amount."""

    def test_moyens_paiement_renvoie_400_si_prix_libre_invalide(
        self, admin_user, tenant, pv_et_produits,
    ):
        """POST /laboutik/paiement/moyens_paiement/ renvoie HTTP 400
        quand le montant libre est inférieur au minimum.
        / POST /laboutik/paiement/moyens_paiement/ returns HTTP 400
        when free price amount is below minimum."""
        with schema_context(TENANT_SCHEMA):
            pv = pv_et_produits['pv']
            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(pv.uuid),
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '100',  # minimum = 500
            }

            response = client.post(
                '/laboutik/paiement/moyens_paiement/',
                data=post_data,
            )
            assert response.status_code == 400

    def test_payer_renvoie_400_si_prix_libre_invalide(
        self, admin_user, tenant, pv_et_produits,
    ):
        """POST /laboutik/paiement/payer/ renvoie HTTP 400
        quand le montant libre est inférieur au minimum.
        / POST /laboutik/paiement/payer/ returns HTTP 400
        when free price amount is below minimum."""
        with schema_context(TENANT_SCHEMA):
            pv = pv_et_produits['pv']
            produit = pv_et_produits['produit_libre']
            prix = pv_et_produits['prix_libre']

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(pv.uuid),
                'moyen_paiement': 'espece',
                'total': '100',
                'given_sum': '0',
                f'repid-{produit.uuid}--{prix.uuid}': '1',
                f'custom-{produit.uuid}--{prix.uuid}': '100',  # minimum = 500
            }

            response = client.post(
                '/laboutik/paiement/payer/',
                data=post_data,
            )
            assert response.status_code == 400
