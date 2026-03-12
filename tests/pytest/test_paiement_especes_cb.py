"""
tests/pytest/test_paiement_especes_cb.py — Tests Phase 2 etape 2 : paiement especes/CB.
tests/pytest/test_paiement_especes_cb.py — Tests Phase 2 step 2: cash/credit card payment.

Couvre : _creer_lignes_articles, ProductSold, PriceSold, LigneArticle,
         payer() especes/CB, panier vide, NFC desactive.
Covers: _creer_lignes_articles, ProductSold, PriceSold, LigneArticle,
        payer() cash/CC, empty cart, NFC disabled.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_especes_cb.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest

from decimal import Decimal

from django.conf import settings
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import PointDeVente


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
        email = 'admin-test-paiement@tibillet.localhost'
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
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def premier_produit_et_prix(premier_pv):
    """Premier produit du PV avec son prix.
    / First product of the PV with its price."""
    with schema_context(TENANT_SCHEMA):
        produit = premier_pv.products.filter(
            methode_caisse__isnull=False,
        ).first()
        prix = Price.objects.filter(
            product=produit,
            publish=True,
            asset__isnull=True,
        ).order_by('order').first()
        return produit, prix


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestPaiementEspeces:
    """Tests du paiement en especes.
    / Tests for cash payment."""

    def test_paiement_especes_cree_ligne_article(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """Payer en especes cree une LigneArticle avec payment_method='CA'.
        / Cash payment creates a LigneArticle with payment_method='CA'."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            client = _make_client(admin_user, tenant)

            # Compter les LigneArticle avant le paiement
            # / Count LigneArticle before payment
            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()

            # Simuler le POST du formulaire d'addition
            # / Simulate the addition form POST
            prix_centimes = int(round(prix.prix * 100))
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '0',
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier qu'une LigneArticle a ete creee
            # / Verify that a LigneArticle was created
            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()
            assert nb_lignes_apres == nb_lignes_avant + 1

            # Verifier le contenu de la LigneArticle
            # / Verify the LigneArticle content
            derniere_ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).order_by('-datetime').first()
            assert derniere_ligne.payment_method == PaymentMethod.CASH
            assert derniere_ligne.amount == prix_centimes
            assert derniere_ligne.status == LigneArticle.VALID


@pytest.mark.usefixtures("test_data")
class TestPaiementCB:
    """Tests du paiement par carte bancaire.
    / Tests for credit card payment."""

    def test_paiement_cb_cree_ligne_article(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """Payer par CB cree une LigneArticle avec payment_method='CC'.
        / CC payment creates a LigneArticle with payment_method='CC'."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            client = _make_client(admin_user, tenant)

            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                payment_method=PaymentMethod.CC,
            ).count()

            prix_centimes = int(round(prix.prix * 100))
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'carte_bancaire',
                'total': str(prix_centimes),
                'given_sum': '',
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                payment_method=PaymentMethod.CC,
            ).count()
            assert nb_lignes_apres == nb_lignes_avant + 1


@pytest.mark.usefixtures("test_data")
class TestTotalCentimes:
    """Tests de la precision du calcul en centimes.
    / Tests for centimes calculation precision."""

    def test_total_centimes_correct(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """Le montant dans LigneArticle == int(round(prix * 100)).
        / The amount in LigneArticle == int(round(prix * 100))."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            client = _make_client(admin_user, tenant)

            prix_centimes_attendu = int(round(prix.prix * 100))
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes_attendu * 2),
                'given_sum': '0',
                f'repid-{produit.uuid}': '2',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            derniere_ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).order_by('-datetime').first()
            assert derniere_ligne.amount == prix_centimes_attendu
            assert int(derniere_ligne.qty) == 2


@pytest.mark.usefixtures("test_data")
class TestProductSoldPriceSold:
    """Tests de creation de ProductSold et PriceSold.
    / Tests for ProductSold and PriceSold creation."""

    def test_pricesold_et_productsold_crees(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """Un paiement cree ProductSold et PriceSold intermediaires.
        / A payment creates intermediate ProductSold and PriceSold."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            client = _make_client(admin_user, tenant)

            prix_centimes = int(round(prix.prix * 100))
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '0',
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier que ProductSold existe pour ce produit
            # / Verify ProductSold exists for this product
            assert ProductSold.objects.filter(product=produit, event=None).exists()

            # Verifier que PriceSold existe pour ce prix
            # / Verify PriceSold exists for this price
            product_sold = ProductSold.objects.get(product=produit, event=None)
            assert PriceSold.objects.filter(
                productsold=product_sold, price=prix,
            ).exists()


@pytest.mark.usefixtures("test_data")
class TestPanierVide:
    """Tests du panier vide.
    / Tests for empty cart."""

    def test_panier_vide_pas_de_ligne(
        self, admin_user, tenant, premier_pv,
    ):
        """POST sans articles → pas de LigneArticle creee, reponse 200 (succes vide).
        / POST without articles → no LigneArticle created, 200 response (empty success)."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)

            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()

            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': '0',
                'given_sum': '0',
                # Pas de repid-* → panier vide
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()
            # Aucune nouvelle ligne creee
            # / No new line created
            assert nb_lignes_apres == nb_lignes_avant


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCCarteInconnue:
    """Tests du paiement NFC avec carte inconnue.
    / Tests for NFC payment with unknown card."""

    def test_paiement_nfc_carte_inconnue(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """POST moyen_paiement=nfc + tag_id invalide → message "Carte inconnue".
        / POST moyen_paiement=nfc + invalid tag_id → "Carte inconnue" message."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            client = _make_client(admin_user, tenant)

            prix_centimes = int(round(prix.prix * 100))
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': 'FAKE_TAG',
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Carte inconnue" in contenu


@pytest.mark.usefixtures("test_data")
class TestPaiementAtomique:
    """Tests d'atomicite du paiement.
    / Tests for payment atomicity."""

    def test_product_uuid_inexistant_pas_de_ligne(
        self, admin_user, tenant, premier_pv,
    ):
        """UUID produit inexistant dans le PV → ignore, pas de ligne creee.
        / Non-existent product UUID in PV → ignored, no line created."""
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)

            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()

            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': '100',
                'given_sum': '0',
                'repid-00000000-0000-0000-0000-000000000000': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
            ).count()
            assert nb_lignes_apres == nb_lignes_avant
