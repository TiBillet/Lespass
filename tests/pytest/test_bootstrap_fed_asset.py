"""
Tests du bootstrap de l'infrastructure recharge FED V2.
Tests for the FED V2 refill infrastructure bootstrap.

LOCALISATION : tests/pytest/test_bootstrap_fed_asset.py

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_bootstrap_fed_asset.py -v --api-key dummy

Approche : les tests ne nettoient PAS le tenant federation_fed avant execution.
La commande bootstrap_fed_asset est idempotente, on teste donc l'etat STABLE
apres execution (plutot que de tenter un cleanup cross-schema fragile).

/ Approach: tests do NOT clean the federation_fed tenant before run.
bootstrap_fed_asset is idempotent, we test the STABLE state after execution
(rather than attempting fragile cross-schema cleanup).
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet
from fedow_core.models import Asset
from BaseBillet.models import Product


FEDERATION_SCHEMA = "federation_fed"
ROOT_WALLET_NAME = "Pot central TiBillet FED"


def test_bootstrap_cree_tenant_federation_fed():
    """
    Apres appel, le tenant federation_fed existe avec la bonne categorie.
    / After call, the federation_fed tenant exists with the right category.
    """
    call_command("bootstrap_fed_asset")

    tenant = Client.objects.get(schema_name=FEDERATION_SCHEMA)
    assert tenant.categorie == Client.FED
    assert tenant.name == "Fédération FED"


def test_bootstrap_cree_asset_fed_unique():
    """
    Apres appel, il existe exactement UN Asset de categorie FED (convention
    globale du projet : un seul asset FED partage par tous les tenants).
    / After call, exactly ONE Asset of category FED exists (project convention:
    single FED asset shared across all tenants).
    """
    call_command("bootstrap_fed_asset")

    assets_fed = Asset.objects.filter(category=Asset.FED)
    assert assets_fed.count() == 1

    asset = assets_fed.first()
    assert asset.currency_code == "EUR"
    assert asset.wallet_origin is not None
    assert asset.wallet_origin.name == ROOT_WALLET_NAME


def test_bootstrap_cree_product_et_price_dans_federation_fed():
    """
    Le Product et Price de recharge existent dans le schema federation_fed.
    / The refill Product and Price exist in the federation_fed schema.
    """
    call_command("bootstrap_fed_asset")

    tenant = Client.objects.get(schema_name=FEDERATION_SCHEMA)
    with tenant_context(tenant):
        product = Product.objects.get(categorie_article=Product.RECHARGE_CASHLESS_FED)
        assert product.name == "Recharge monnaie fédérée"

        price = product.prices.first()
        assert price is not None
        assert price.name == "Montant libre"
        assert price.prix == 0


def test_bootstrap_est_idempotent():
    """
    Deux appels successifs ne creent pas de doublons.
    On compte avant/apres pour tester l'idempotence, sans presumer de l'etat initial.
    / Two successive calls do not create duplicates.
    Count before/after to test idempotence, without assuming initial state.
    """
    # Premier appel : garantit que l'etat initial contient les objets.
    # / First call: ensures the initial state has the objects.
    call_command("bootstrap_fed_asset")

    tenants_avant = Client.objects.filter(schema_name=FEDERATION_SCHEMA).count()
    assets_avant = Asset.objects.filter(category=Asset.FED).count()
    wallets_avant = Wallet.objects.filter(name=ROOT_WALLET_NAME).count()

    tenant = Client.objects.get(schema_name=FEDERATION_SCHEMA)
    with tenant_context(tenant):
        products_avant = Product.objects.filter(
            categorie_article=Product.RECHARGE_CASHLESS_FED
        ).count()

    # Deuxieme appel : ne doit rien creer en plus.
    # / Second call: must not create anything extra.
    call_command("bootstrap_fed_asset")

    assert Client.objects.filter(schema_name=FEDERATION_SCHEMA).count() == tenants_avant
    assert Asset.objects.filter(category=Asset.FED).count() == assets_avant
    assert Wallet.objects.filter(name=ROOT_WALLET_NAME).count() == wallets_avant

    with tenant_context(tenant):
        assert (
            Product.objects.filter(
                categorie_article=Product.RECHARGE_CASHLESS_FED
            ).count()
            == products_avant
        )

    # Verification stricte : UN SEUL de chaque (convention globale projet).
    # / Strict check: exactly ONE of each (project-wide convention).
    assert tenants_avant == 1
    assert assets_avant == 1
    assert wallets_avant == 1
    assert products_avant == 1
