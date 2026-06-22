"""
tests/pytest/test_asset_recharge_signal.py — Tests du signal post_save Asset.
Verifie que la creation d'un Asset TLF/TNF/TIM cree automatiquement
un Product de recharge avec 4 Prices et l'attache aux PV CASHLESS.

/ Tests for Asset post_save signal.
Verifies that creating a TLF/TNF/TIM Asset auto-creates a top-up
Product with 4 Prices and attaches it to CASHLESS POS.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_asset_recharge_signal.py -v
"""

import sys

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest  # noqa: E402
from decimal import Decimal  # noqa: E402

from django_tenants.utils import schema_context  # noqa: E402

from AuthBillet.models import Wallet  # noqa: E402
from BaseBillet.models import Price, Product  # noqa: E402
from Customers.models import Client  # noqa: E402
from fedow_core.models import Asset  # noqa: E402
from fedow_core.services import AssetService  # noqa: E402
from laboutik.models import PointDeVente  # noqa: E402


TENANT_SCHEMA = "lespass"


def _nettoyer_product_et_asset(produit, asset):
    """Supprime proprement un Product (et ses Prices) puis l'Asset associe.
    / Cleanly deletes a Product (and its Prices) then the associated Asset."""
    Price.objects.filter(product=produit).delete()
    produit.delete()
    asset.delete()


@pytest.fixture(scope="module")
def tenant():
    return Client.objects.get(schema_name=TENANT_SCHEMA)


@pytest.fixture(scope="module")
def wallet_lieu(tenant):
    """Wallet du lieu pour les Assets.
    / Venue wallet for Assets."""
    # Plusieurs wallets peuvent exister pour ce tenant, on prend le premier
    # / Multiple wallets may exist for this tenant, take the first one
    wallet = Wallet.objects.filter(origin=tenant).first()
    if wallet is None:
        wallet = Wallet.objects.create(
            origin=tenant,
            name=f"[test_signal] {tenant.name}",
        )
    return wallet


@pytest.fixture(scope="module")
def pv_cashless():
    """Point de vente CASHLESS pour verifier l'auto-attachement.
    / CASHLESS POS to verify auto-attachment."""
    with schema_context(TENANT_SCHEMA):
        pv, _ = PointDeVente.objects.get_or_create(
            name="[test_signal] PV Cashless",
            defaults={
                "comportement": PointDeVente.CASHLESS,
                "service_direct": True,
            },
        )
        return pv


# --- Tests creation ---


def test_creation_asset_tlf_cree_product_recharge(tenant, wallet_lieu, pv_cashless):
    """Creer un Asset TLF → un Product RE avec 4 Prices doit apparaitre.
    / Creating a TLF Asset → a RE Product with 4 Prices must appear."""
    with schema_context(TENANT_SCHEMA):
        asset_tlf = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Monnaie locale",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_tlf).first()
        assert produit is not None, "Le signal n'a pas cree de Product pour l'Asset TLF"
        assert produit.methode_caisse == Product.RECHARGE_EUROS
        assert "Recharge" in produit.name
        assert produit.archive is False

        prices = list(Price.objects.filter(product=produit).order_by("order"))
        assert len(prices) == 4, f"Attendu 4 Prices, trouve {len(prices)}"
        assert prices[0].prix == Decimal("1.00")
        assert prices[1].prix == Decimal("5.00")
        assert prices[2].prix == Decimal("10.00")
        assert prices[3].free_price is True

        assert pv_cashless.products.filter(pk=produit.pk).exists(), (
            "Le Product n'a pas ete ajoute au PV CASHLESS"
        )

        _nettoyer_product_et_asset(produit, asset_tlf)


def test_creation_asset_tnf_cree_product_cadeau(tenant, wallet_lieu):
    """Creer un Asset TNF → un Product RC doit apparaitre.
    / Creating a TNF Asset → a RC Product must appear."""
    with schema_context(TENANT_SCHEMA):
        asset_tnf = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Cadeau",
            category=Asset.TNF,
            currency_code="CAD",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_tnf).first()
        assert produit is not None
        assert produit.methode_caisse == Product.RECHARGE_CADEAU
        assert "cadeau" in produit.name.lower()

        _nettoyer_product_et_asset(produit, asset_tnf)


def test_creation_asset_tim_cree_product_temps(tenant, wallet_lieu):
    """Creer un Asset TIM → un Product TM doit apparaitre.
    / Creating a TIM Asset → a TM Product must appear."""
    with schema_context(TENANT_SCHEMA):
        asset_tim = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Temps",
            category=Asset.TIM,
            currency_code="TMP",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_tim).first()
        assert produit is not None
        assert produit.methode_caisse == Product.RECHARGE_TEMPS

        _nettoyer_product_et_asset(produit, asset_tim)


def test_creation_asset_fed_ne_cree_pas_product(tenant, wallet_lieu):
    """Creer un Asset FED → aucun Product ne doit etre cree.
    / Creating a FED Asset → no Product should be created."""
    with schema_context(TENANT_SCHEMA):
        asset_fed = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Stripe Fed",
            category=Asset.FED,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.filter(asset=asset_fed).first()
        assert produit is None, "Le signal a cree un Product pour un Asset FED"

        asset_fed.delete()


# --- Tests archivage ---


def test_archivage_asset_archive_product(tenant, wallet_lieu):
    """Archiver un Asset → le Product doit etre archive.
    / Archiving an Asset → the Product must be archived."""
    with schema_context(TENANT_SCHEMA):
        asset = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Archive Test",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.get(asset=asset)
        assert produit.archive is False

        asset.archive = True
        asset.save(update_fields=["archive"])
        produit.refresh_from_db()
        assert produit.archive is True

        asset.archive = False
        asset.save(update_fields=["archive"])
        produit.refresh_from_db()
        assert produit.archive is False

        _nettoyer_product_et_asset(produit, asset)


def test_renommage_asset_met_a_jour_product(tenant, wallet_lieu):
    """Renommer un Asset → le Product doit etre renomme.
    / Renaming an Asset → the Product must be renamed."""
    with schema_context(TENANT_SCHEMA):
        asset = AssetService.creer_asset(
            tenant=tenant,
            name="[test_signal] Avant",
            category=Asset.TLF,
            currency_code="EUR",
            wallet_origin=wallet_lieu,
        )

        produit = Product.objects.get(asset=asset)
        assert "Avant" in produit.name

        asset.name = "[test_signal] Apres"
        asset.save(update_fields=["name"])
        produit.refresh_from_db()
        assert "Apres" in produit.name

        _nettoyer_product_et_asset(produit, asset)
