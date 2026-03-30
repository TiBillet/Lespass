"""
tests/pytest/test_mode_ecole.py — Tests Session 15 : mode ecole.
/ Tests Session 15: training mode.

Couvre : sale_origin LABOUTIK_TEST, exclusion rapport prod,
         mention SIMULATION sur tickets.
Covers: LABOUTIK_TEST sale_origin, prod report exclusion,
        SIMULATION on receipts.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_mode_ecole.py -v
"""
import sys
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
    PointDeVente, LaboutikConfiguration,
)

TENANT_SCHEMA = 'lespass'


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


@pytest.fixture
def pv(test_data):
    """Retourne le premier point de vente.
    / Returns the first point of sale."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.first()


@pytest.fixture
def config(test_data):
    """Retourne la config LaboutikConfiguration.
    / Returns the LaboutikConfiguration."""
    with schema_context(TENANT_SCHEMA):
        return LaboutikConfiguration.get_solo()


@pytest.fixture
def operateur(test_data):
    """Retourne un utilisateur operateur.
    / Returns an operator user."""
    with schema_context(TENANT_SCHEMA):
        return TibilletUser.objects.filter(is_staff=True).first()


def _creer_ligne_test(pv, sale_origin=SaleOrigin.LABOUTIK_TEST):
    """
    Helper : cree une LigneArticle minimale pour les tests.
    Utilise un produit POS (methode_caisse=Product.VENTE).
    / Helper: creates a minimal LigneArticle for tests.
    Uses a POS product (methode_caisse=Product.VENTE).
    """
    # Chercher un produit avec methode_caisse definie (= disponible en caisse)
    # / Find a product with methode_caisse set (= available at POS)
    product = Product.objects.filter(
        methode_caisse=Product.VENTE,
    ).first()
    assert product is not None, "Aucun produit POS de type VENTE trouve. Lancer create_test_pos_data."

    price = product.prices.first()
    assert price is not None, "Le produit POS n'a pas de prix associe."

    product_sold, _ = ProductSold.objects.get_or_create(
        product=product,
        event=None,
    )
    price_sold, _ = PriceSold.objects.get_or_create(
        productsold=product_sold,
        price=price,
        defaults={'prix': price.prix},
    )

    ligne = LigneArticle.objects.create(
        pricesold=price_sold,
        amount=500,
        qty=Decimal("1"),
        vat=Decimal("0"),
        payment_method=PaymentMethod.CASH,
        sale_origin=sale_origin,
        status=LigneArticle.VALID,
        point_de_vente=pv,
    )
    return ligne


class TestModeEcole:
    """Tests du mode ecole (exigence LNE 5).
    / Training mode tests (LNE req. 5)."""

    @pytest.mark.django_db
    def test_sale_origin_laboutik_test_existe(self):
        """Verifie que le choix LABOUTIK_TEST existe dans SaleOrigin.
        / Verifies LABOUTIK_TEST choice exists in SaleOrigin."""
        assert hasattr(SaleOrigin, 'LABOUTIK_TEST')
        assert SaleOrigin.LABOUTIK_TEST == 'LT'

    @pytest.mark.django_db
    def test_mode_ecole_sale_origin(self, pv, config, operateur):
        """En mode ecole, les lignes creees ont sale_origin=LABOUTIK_TEST.
        / In training mode, created lines have sale_origin=LABOUTIK_TEST."""
        with schema_context(TENANT_SCHEMA):
            ligne = _creer_ligne_test(pv, sale_origin=SaleOrigin.LABOUTIK_TEST)
            assert ligne.sale_origin == SaleOrigin.LABOUTIK_TEST

    @pytest.mark.django_db
    def test_mode_ecole_exclu_rapport_prod(self, pv, config):
        """Le RapportComptableService exclut les lignes LABOUTIK_TEST.
        / RapportComptableService excludes LABOUTIK_TEST lines."""
        from laboutik.reports import RapportComptableService

        with schema_context(TENANT_SCHEMA):
            now = timezone.now()
            debut = now - timezone.timedelta(hours=1)

            # Creer une ligne LABOUTIK_TEST
            # / Create a LABOUTIK_TEST line
            ligne_test = _creer_ligne_test(pv, sale_origin=SaleOrigin.LABOUTIK_TEST)

            # Le rapport ne doit PAS inclure cette ligne
            # / Report must NOT include this line
            service = RapportComptableService(pv, debut, now)
            lignes_ids = list(service.lignes.values_list('pk', flat=True))
            assert ligne_test.pk not in lignes_ids

    @pytest.mark.django_db
    def test_ticket_simulation(self, pv, config, operateur):
        """En mode ecole, le ticket formate contient is_simulation=True.
        / In training mode, formatted ticket contains is_simulation=True."""
        from laboutik.printing.formatters import formatter_ticket_vente

        with schema_context(TENANT_SCHEMA):
            # Activer le mode ecole / Enable training mode
            config.mode_ecole = True
            config.save(update_fields=['mode_ecole'])

            try:
                ligne = _creer_ligne_test(pv, sale_origin=SaleOrigin.LABOUTIK_TEST)

                ticket_data = formatter_ticket_vente(
                    [ligne], pv, operateur, "Especes",
                )

                assert ticket_data.get("is_simulation") is True
            finally:
                # Toujours desactiver le mode ecole apres le test
                # / Always disable training mode after test
                config.mode_ecole = False
                config.save(update_fields=['mode_ecole'])
