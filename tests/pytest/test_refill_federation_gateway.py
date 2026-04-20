"""
Tests de la gateway Stripe dediee a la recharge FED V2.
Tests for the Stripe gateway dedicated to V2 FED refill.

LOCALISATION : tests/pytest/test_refill_federation_gateway.py

Tests critiques (Phase B) :
- Pas de Stripe Connect : `stripe_account` ABSENT du dict envoye a Stripe
- Pas de SEPA : `payment_method_types == ['card']` uniquement
- `Paiement_stripe.source == CASHLESS_REFILL`
- Metadata contient bien `refill_type='FED'` + tenant + paiement_uuid + wallet + asset

/ Critical tests (Phase B):
- No Stripe Connect: `stripe_account` ABSENT from dict sent to Stripe
- No SEPA: `payment_method_types == ['card']` only
- `Paiement_stripe.source == CASHLESS_REFILL`
- Metadata contains `refill_type='FED'` + tenant + paiement_uuid + wallet + asset

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_refill_federation_gateway.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.management import call_command
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from fedow_core.models import Asset
from BaseBillet.models import Product, LigneArticle, PaymentMethod, Paiement_stripe
from ApiBillet.serializers import get_or_create_price_sold
from PaiementStripe.refill_federation import CreationPaiementStripeFederation


TEST_PREFIX = "[test_refill_gateway]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """Bootstrape federation_fed (idempotent)."""
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def asset_fed(tenant_federation_fed):
    return Asset.objects.get(category=Asset.FED)


@pytest.fixture
def user_avec_wallet(tenant_federation_fed):
    """User unique par test (UUID dans email) + wallet dans federation_fed."""
    email = f"{TEST_PREFIX} {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


@pytest.fixture
def ligne_article_refill(tenant_federation_fed, asset_fed):
    """
    LigneArticle de recharge creee dans le schema federation_fed.
    On s'appuie sur le Product/Price deja cree par bootstrap_fed_asset.
    / LigneArticle for refill, created in federation_fed schema.
    Uses the Product/Price already created by bootstrap_fed_asset.
    """
    from decimal import Decimal

    with tenant_context(tenant_federation_fed):
        product_refill = Product.objects.get(
            categorie_article=Product.RECHARGE_CASHLESS_FED
        )
        price_refill = product_refill.prices.first()

        # Montant en euros pour PriceSold (Decimal) ; correspond a 15,00 EUR = 1500 cts.
        # / Amount in euros for PriceSold (Decimal); 15.00 EUR = 1500 cents.
        pricesold = get_or_create_price_sold(
            price_refill,
            custom_amount=Decimal("15.00"),
        )

        ligne = LigneArticle.objects.create(
            pricesold=pricesold,
            amount=1500,  # 15,00 EUR en centimes
            qty=1,
            payment_method=PaymentMethod.STRIPE_FED,
        )

    return ligne


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_gateway_no_stripe_connect(
    mock_stripe,
    user_avec_wallet,
    asset_fed,
    tenant_federation_fed,
    ligne_article_refill,
):
    """
    Le dict envoye a stripe.checkout.Session.create NE contient PAS `stripe_account`.
    Recharge FED = compte central, pas un compte Connect de lieu.
    / Dict sent to Stripe does NOT contain `stripe_account`.
    """
    with tenant_context(tenant_federation_fed):
        gateway = CreationPaiementStripeFederation(
            user=user_avec_wallet,
            liste_ligne_article=[ligne_article_refill],
            wallet_receiver=user_avec_wallet.wallet,
            asset_fed=asset_fed,
            tenant_federation=tenant_federation_fed,
            absolute_domain="https://lespass.tibillet.localhost/my_account/",
        )

    assert gateway.is_valid()

    # Verifie l'appel Stripe
    # / Inspect Stripe call
    assert mock_stripe.mock_create.called
    call_kwargs = mock_stripe.mock_create.call_args.kwargs
    assert "stripe_account" not in call_kwargs, (
        f"stripe_account ne doit PAS etre present pour une recharge FED V2. "
        f"Trouve : {call_kwargs.get('stripe_account')}"
    )


def test_gateway_no_sepa(
    mock_stripe,
    user_avec_wallet,
    asset_fed,
    tenant_federation_fed,
    ligne_article_refill,
):
    """
    `payment_method_types == ['card']` uniquement. Pas de SEPA (UX immediate).
    / `payment_method_types == ['card']` only. No SEPA (immediate UX).
    """
    with tenant_context(tenant_federation_fed):
        CreationPaiementStripeFederation(
            user=user_avec_wallet,
            liste_ligne_article=[ligne_article_refill],
            wallet_receiver=user_avec_wallet.wallet,
            asset_fed=asset_fed,
            tenant_federation=tenant_federation_fed,
            absolute_domain="https://lespass.tibillet.localhost/my_account/",
        )

    call_kwargs = mock_stripe.mock_create.call_args.kwargs
    assert call_kwargs["payment_method_types"] == ["card"], (
        f"payment_method_types doit etre ['card'] uniquement. "
        f"Trouve : {call_kwargs['payment_method_types']}"
    )


def test_gateway_cree_paiement_stripe_avec_source_cashless_refill(
    mock_stripe,
    user_avec_wallet,
    asset_fed,
    tenant_federation_fed,
    ligne_article_refill,
):
    """
    Le Paiement_stripe cree a bien source=CASHLESS_REFILL et status=PENDING.
    / Created Paiement_stripe has source=CASHLESS_REFILL and status=PENDING.
    """
    with tenant_context(tenant_federation_fed):
        gateway = CreationPaiementStripeFederation(
            user=user_avec_wallet,
            liste_ligne_article=[ligne_article_refill],
            wallet_receiver=user_avec_wallet.wallet,
            asset_fed=asset_fed,
            tenant_federation=tenant_federation_fed,
            absolute_domain="https://lespass.tibillet.localhost/my_account/",
        )
        paiement = gateway.paiement_stripe_db

    assert paiement.source == Paiement_stripe.CASHLESS_REFILL
    # Status PENDING : le webhook Stripe le passera a PAID apres paiement.
    # / Status PENDING: Stripe webhook will flip to PAID after payment.
    assert paiement.status == Paiement_stripe.PENDING
    # La session Stripe est persistee
    # / Stripe session is persisted
    assert paiement.checkout_session_id_stripe == "cs_test_mock_session"
    assert paiement.checkout_session_url is not None


def test_gateway_injecte_metadata_refill_type_fed(
    mock_stripe,
    user_avec_wallet,
    asset_fed,
    tenant_federation_fed,
    ligne_article_refill,
):
    """
    La metadata envoyee a Stripe contient les cles requises par PSP_INTERFACE.md :
    tenant, paiement_stripe_uuid, refill_type='FED', wallet_receiver_uuid, asset_uuid.
    / Metadata sent to Stripe contains keys required by PSP_INTERFACE.md.
    """
    with tenant_context(tenant_federation_fed):
        gateway = CreationPaiementStripeFederation(
            user=user_avec_wallet,
            liste_ligne_article=[ligne_article_refill],
            wallet_receiver=user_avec_wallet.wallet,
            asset_fed=asset_fed,
            tenant_federation=tenant_federation_fed,
            absolute_domain="https://lespass.tibillet.localhost/my_account/",
        )
        paiement_uuid = str(gateway.paiement_stripe_db.uuid)

    call_kwargs = mock_stripe.mock_create.call_args.kwargs
    metadata = call_kwargs["metadata"]

    assert metadata["refill_type"] == "FED"
    assert metadata["tenant"] == str(tenant_federation_fed.uuid)
    assert metadata["paiement_stripe_uuid"] == paiement_uuid
    assert metadata["wallet_receiver_uuid"] == str(user_avec_wallet.wallet.uuid)
    assert metadata["asset_uuid"] == str(asset_fed.uuid)
