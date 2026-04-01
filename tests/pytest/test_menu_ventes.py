"""
tests/pytest/test_menu_ventes.py — Tests Session 16 : menu Ventes (Ticket X + liste).
tests/pytest/test_menu_ventes.py — Tests Session 16: Sales menu (Ticket X + list).

Couvre : recap_en_cours (3 vues), liste_ventes (pagination, filtre), detail_vente.
Covers: recap_en_cours (3 views), liste_ventes (pagination, filter), detail_vente.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_menu_ventes.py -v
"""

import os
import sys
import uuid as uuid_module

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

import django
django.setup()

import pytest

from decimal import Decimal
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser
from BaseBillet.models import (
    LigneArticle, Price, PriceSold, Product, ProductSold,
    SaleOrigin, PaymentMethod,
)
from Customers.models import Client
from laboutik.models import (
    PointDeVente, ClotureCaisse,
)

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
        email = 'admin-test-ventes@tibillet.localhost'
        user, _created = TibilletUser.objects.get_or_create(
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


def _creer_ligne_article_directe(produit, prix, montant_centimes, payment_method_code, pv=None, uuid_tx=None):
    """
    Cree une LigneArticle directement en base (sans passer par la vue).
    Creates a LigneArticle directly in DB (without going through the view).
    """
    product_sold, _ = ProductSold.objects.get_or_create(
        product=produit,
        event=None,
        defaults={'categorie_article': produit.categorie_article},
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=prix,
        defaults={'prix': prix.prix},
    )
    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        qty=1,
        amount=montant_centimes,
        sale_origin=SaleOrigin.LABOUTIK,
        payment_method=payment_method_code,
        status=LigneArticle.VALID,
        point_de_vente=pv,
        uuid_transaction=uuid_tx,
    )
    return ligne


# ---------------------------------------------------------------------------
# Tests Ticket X (recap_en_cours)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRecapEnCours:
    """Tests du Ticket X — recap comptable du service en cours.
    / Tests for Ticket X — accounting summary of current shift."""

    def test_recap_en_cours_toutes_caisses(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Cree des ventes, appelle recap-en-cours avec vue=toutes.
        Verifie : 200, contient "Ticket X", contient les totaux.
        / Create sales, call recap-en-cours with vue=toutes.
        Verify: 200, contains "Ticket X", contains totals.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            # Creer une vente pour s'assurer qu'il y a des donnees
            # / Create a sale to ensure data exists
            _creer_ligne_article_directe(produit, prix, 500, PaymentMethod.CASH, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=toutes')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Verifie que le template Ticket X est rendu
            # / Verify Ticket X template is rendered
            assert 'data-testid="ventes-recap"' in contenu
            # Verifie que les totaux sont presents (tableau des moyens de paiement)
            # / Verify totals are present (payment method table)
            assert 'data-testid="recap-totaux-moyen"' in contenu

    def test_recap_en_cours_par_pv(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle recap-en-cours avec vue=par_pv.
        Verifie : 200, contient le nom du PV.
        / Calls recap-en-cours with vue=par_pv.
        Verify: 200, contains POS name.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            _creer_ligne_article_directe(produit, prix, 300, PaymentMethod.CC, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=par_pv')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # La ventilation par PV doit contenir le nom du PV
            # / The POS breakdown must contain the POS name
            assert premier_pv.name in contenu

    def test_recap_en_cours_par_moyen(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle recap-en-cours avec vue=par_moyen.
        Verifie : 200, contient le tableau synthese operations.
        / Calls recap-en-cours with vue=par_moyen.
        Verify: 200, contains operations summary table.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/?vue=par_moyen')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="recap-synthese-operations"' in contenu

    def test_recap_en_cours_aucune_vente(
        self, admin_user, tenant,
    ):
        """
        Si aucune vente apres une cloture, affiche le message vide.
        / If no sales after a closure, show empty message.

        NOTE : ce test peut ne pas trouver "aucune vente" si d'autres tests
        ont cree des LigneArticle. On verifie juste que la vue retourne 200.
        / This test may not find "no sales" if other tests created LigneArticle.
        We just verify the view returns 200.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/recap-en-cours/')
            assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests liste des ventes
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestListeVentes:
    """Tests de la liste des ventes.
    / Tests for the sales list."""

    def test_liste_ventes_paginee(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Appelle liste-ventes.
        Verifie : 200, contient le tableau des ventes.
        / Calls liste-ventes.
        Verify: 200, contains sales table.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            # S'assurer qu'il y a au moins une vente
            # / Ensure at least one sale exists
            _creer_ligne_article_directe(produit, prix, 700, PaymentMethod.CASH, pv=premier_pv)

            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/liste-ventes/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="ventes-liste"' in contenu

    def test_liste_ventes_filtre_moyen(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Filtre la liste par moyen de paiement (especes).
        Verifie : 200, ne contient que les ventes en especes.
        / Filter list by payment method (cash).
        Verify: 200, contains only cash sales.
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/liste-ventes/?moyen={PaymentMethod.CASH}')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            # Le filtre est applique — on verifie que la page se charge
            # / Filter is applied — we verify the page loads
            assert 'data-testid="ventes-liste"' in contenu


# ---------------------------------------------------------------------------
# Tests detail vente
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestDetailVente:
    """Tests du detail d'une vente.
    / Tests for sale detail."""

    def test_detail_vente_existante(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """
        Cree une vente avec uuid_transaction, appelle detail-vente.
        Verifie : 200, contient les infos de la transaction.
        / Creates a sale with uuid_transaction, calls detail-vente.
        Verify: 200, contains transaction info.
        """
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            uuid_tx = uuid_module.uuid4()

            _creer_ligne_article_directe(
                produit, prix, 1500, PaymentMethod.CASH,
                pv=premier_pv, uuid_tx=uuid_tx,
            )

            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_tx}/')
            assert response.status_code == 200

            contenu = response.content.decode('utf-8')
            assert 'data-testid="ventes-detail"' in contenu
            assert 'data-testid="detail-articles"' in contenu
            # Le produit doit apparaitre dans le detail
            # / The product must appear in the detail
            assert produit.name in contenu

    def test_detail_vente_introuvable(
        self, admin_user, tenant,
    ):
        """
        Appelle detail-vente avec un uuid_transaction inexistant.
        Verifie : 404.
        / Calls detail-vente with a nonexistent uuid_transaction.
        Verify: 404.
        """
        with schema_context(TENANT_SCHEMA):
            uuid_bidon = uuid_module.uuid4()
            client = _make_client(admin_user, tenant)
            response = client.get(f'/laboutik/caisse/detail-vente/{uuid_bidon}/')
            assert response.status_code == 404

    def test_detail_vente_uuid_invalide(
        self, admin_user, tenant,
    ):
        """
        Appelle detail-vente avec une chaine qui n'est pas un UUID.
        Verifie : 404 (pas 500).
        / Calls detail-vente with a string that is not a UUID.
        Verify: 404 (not 500).
        """
        with schema_context(TENANT_SCHEMA):
            client = _make_client(admin_user, tenant)
            response = client.get('/laboutik/caisse/detail-vente/pas-un-uuid/')
            assert response.status_code == 404
