"""
Tests du RefillService.process_cashless_refill.
Tests for RefillService.process_cashless_refill.

LOCALISATION : tests/pytest/test_refill_service.py

Tests critiques (Phase A) :
- nominal : Transaction REFILL creee, Token credite
- idempotent : 2 appels -> 1 seule Transaction
- fallback wallet : si user.wallet is None, wallet cree automatiquement

/ Critical tests (Phase A):
- nominal: REFILL Transaction created, Token credited
- idempotent: 2 calls -> 1 Transaction
- wallet fallback: if user.wallet is None, wallet auto-created

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_refill_service.py -v --api-key dummy
"""

import sys
import uuid

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.management import call_command

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import RefillService


TEST_PREFIX = "[test_refill_service]"


@pytest.fixture(scope="module")
def tenant_federation_fed():
    """
    Bootstrape federation_fed et retourne le tenant.
    Idempotent : reutilise si deja present.
    / Bootstraps federation_fed and returns the tenant. Idempotent.
    """
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture
def user_avec_wallet(tenant_federation_fed):
    """
    User dont le wallet pointe vers federation_fed (cas V2 nominal).
    Cree un user unique par test (UUID dans email) pour eviter les collisions.
    / User with wallet pointing to federation_fed (nominal V2 case).
    Unique user per test to avoid collisions.
    """
    email = f"{TEST_PREFIX} {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])
    return user


@pytest.fixture
def user_sans_wallet():
    """
    User sans wallet (edge case pour tester le fallback defensif).
    / User without wallet (edge case for defensive fallback).
    """
    email = f"{TEST_PREFIX} no_wallet {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    return user


def test_refill_service_nominal(tenant_federation_fed, user_avec_wallet):
    """
    Appel nominal : la Transaction REFILL est creee et le Token credite.
    / Nominal call: REFILL Transaction created and Token credited.
    """
    paiement_uuid = uuid.uuid4()
    amount_cents = 1500  # 15,00 EUR

    transaction_creee = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip="127.0.0.1",
    )

    # La Transaction existe avec les bonnes valeurs.
    # / Transaction exists with the right values.
    assert transaction_creee is not None
    assert transaction_creee.action == Transaction.REFILL
    assert transaction_creee.amount == amount_cents
    assert transaction_creee.receiver == user_avec_wallet.wallet
    assert str(transaction_creee.checkout_stripe) == str(paiement_uuid)

    # Le Token est credite du montant.
    # / Token is credited.
    asset_fed = Asset.objects.get(category=Asset.FED)
    token = Token.objects.get(wallet=user_avec_wallet.wallet, asset=asset_fed)
    assert token.value == amount_cents


def test_refill_service_idempotent(tenant_federation_fed, user_avec_wallet):
    """
    Deux appels successifs avec le meme paiement_uuid : une seule Transaction,
    Token credite une seule fois.
    / Two successive calls with same paiement_uuid: one Transaction, credit once.
    """
    paiement_uuid = uuid.uuid4()
    amount_cents = 2000

    tx1 = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip="127.0.0.1",
    )
    tx2 = RefillService.process_cashless_refill(
        paiement_uuid=paiement_uuid,
        user=user_avec_wallet,
        amount_cents=amount_cents,
        tenant=tenant_federation_fed,
        ip="127.0.0.1",
    )

    # Meme Transaction retournee.
    # / Same Transaction returned.
    assert tx1.pk == tx2.pk

    # Une seule Transaction en base pour ce paiement_uuid.
    # / Only one Transaction in DB for this paiement_uuid.
    transactions = Transaction.objects.filter(
        checkout_stripe=paiement_uuid,
        action=Transaction.REFILL,
    )
    assert transactions.count() == 1

    # Le Token n'est pas credite deux fois.
    # / Token is not credited twice.
    asset_fed = Asset.objects.get(category=Asset.FED)
    token = Token.objects.get(wallet=user_avec_wallet.wallet, asset=asset_fed)
    assert token.value == amount_cents  # pas 2 * amount_cents


def test_refill_service_cree_wallet_si_absent(tenant_federation_fed, user_sans_wallet):
    """
    Fallback defensif : si user.wallet is None, le wallet est cree automatiquement.
    / Defensive fallback: if user.wallet is None, wallet auto-created.
    """
    assert user_sans_wallet.wallet is None

    RefillService.process_cashless_refill(
        paiement_uuid=uuid.uuid4(),
        user=user_sans_wallet,
        amount_cents=500,
        tenant=tenant_federation_fed,
        ip="127.0.0.1",
    )

    # Le wallet a ete cree avec origin=federation_fed.
    # / Wallet was created with origin=federation_fed.
    user_sans_wallet.refresh_from_db()
    assert user_sans_wallet.wallet is not None
    assert user_sans_wallet.wallet.origin == tenant_federation_fed
