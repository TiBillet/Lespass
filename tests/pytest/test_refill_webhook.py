"""
Tests du dispatch webhook Stripe et du handler recharge FED V2.
Tests for the Stripe webhook dispatch and the V2 FED refill handler.

LOCALISATION : tests/pytest/test_refill_webhook.py

Depuis la refonte "pattern webhook+retour", la logique metier vit dans
`traiter_paiement_cashless_refill()` (ApiBillet/views.py). Cette fonction
appelle `stripe.checkout.Session.retrieve()` pour avoir le vrai status —
on mocke cet appel via la fixture `mock_stripe`.

/ Since the "webhook+return pattern" refactor, business logic lives in
`traiter_paiement_cashless_refill()`. It calls `stripe.checkout.Session.retrieve()`
to get the real status — mocked via `mock_stripe` fixture.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_refill_webhook.py -v --api-key dummy
"""

import sys
import uuid
from decimal import Decimal

sys.path.insert(0, "/DjangoFiles")

import django

django.setup()

import pytest
from django.core.management import call_command
from django.test import RequestFactory
from django_tenants.utils import tenant_context

from Customers.models import Client
from AuthBillet.models import Wallet, TibilletUser
from fedow_core.models import Asset, Transaction
from BaseBillet.models import Product, LigneArticle, PaymentMethod, Paiement_stripe
from ApiBillet.serializers import get_or_create_price_sold
from ApiBillet.views import _process_stripe_webhook_cashless_refill


TEST_PREFIX = "[test_refill_webhook]"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tenant_federation_fed():
    call_command("bootstrap_fed_asset")
    return Client.objects.get(schema_name="federation_fed")


@pytest.fixture(scope="module")
def asset_fed(tenant_federation_fed):
    return Asset.objects.get(category=Asset.FED)


@pytest.fixture
def paiement_refill(tenant_federation_fed, asset_fed):
    """
    Cree un Paiement_stripe + LigneArticle valides pour le webhook.
    Montant : 1500 centimes (15,00 EUR).
    checkout_session_id_stripe = "cs_test_mock_session" (valeur du fake_session
    de la fixture mock_stripe).
    / Creates valid Paiement_stripe + LigneArticle. Amount: 1500 cents.
    checkout_session_id_stripe matches mock_stripe fixture.
    """
    email = f"{TEST_PREFIX} {uuid.uuid4()}@test.local"
    user = TibilletUser.objects.create(email=email, username=email)
    user.wallet = Wallet.objects.create(
        origin=tenant_federation_fed,
        name=f"Wallet {email}",
    )
    user.save(update_fields=["wallet"])

    with tenant_context(tenant_federation_fed):
        product_refill = Product.objects.get(
            categorie_article=Product.RECHARGE_CASHLESS_FED
        )
        price_refill = product_refill.prices.first()

        pricesold = get_or_create_price_sold(
            price_refill,
            custom_amount=Decimal("15.00"),
        )

        paiement = Paiement_stripe.objects.create(
            user=user,
            source=Paiement_stripe.CASHLESS_REFILL,
            status=Paiement_stripe.PENDING,
            checkout_session_id_stripe="cs_test_mock_session",
        )
        LigneArticle.objects.create(
            pricesold=pricesold,
            amount=1500,
            qty=1,
            payment_method=PaymentMethod.STRIPE_FED,
            paiement_stripe=paiement,
        )

    return paiement


def _build_webhook_payload(paiement, tenant_federation, wallet_uuid=None, asset_uuid=None):
    """
    Construit un payload Stripe minimal (seules les metadata sont lues par le
    dispatcher, le traitement metier interroge Stripe via retrieve()).
    / Builds a minimal Stripe payload (only metadata is read by dispatcher;
    business processing calls Stripe.retrieve()).
    """
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_mock_session",
                "success_url": "https://lespass.example.com/my_account/xxx/return_refill_wallet/",
                "metadata": {
                    "tenant": str(tenant_federation.uuid),
                    "paiement_stripe_uuid": str(paiement.uuid),
                    "refill_type": "FED",
                    "wallet_receiver_uuid": str(wallet_uuid)
                    if wallet_uuid
                    else str(paiement.user.wallet.uuid),
                    "asset_uuid": str(asset_uuid) if asset_uuid else "",
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_webhook_dispatch_cashless_refill(
    mock_stripe, tenant_federation_fed, asset_fed, paiement_refill
):
    """
    Webhook nominal : le dispatcher appelle traiter_paiement_cashless_refill,
    qui interroge Stripe (mocke : payment_status=paid + amount_total=1500),
    cree la Transaction REFILL et passe Paiement_stripe.status=PAID.
    """
    # Stripe (mocke) dit : paid, amount = 1500 cents.
    # / Stripe (mocked): paid, amount = 1500 cents.
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    payload = _build_webhook_payload(paiement_refill, tenant_federation_fed, asset_uuid=asset_fed.uuid)
    request = RequestFactory().post("/webhook/stripe/")

    response = _process_stripe_webhook_cashless_refill(payload, request)

    assert response.status_code == 200

    with tenant_context(tenant_federation_fed):
        paiement_refill.refresh_from_db()
        assert paiement_refill.status == Paiement_stripe.PAID

    transactions = Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    )
    assert transactions.count() == 1
    assert transactions.first().amount == 1500


def test_webhook_anti_tampering(
    mock_stripe, tenant_federation_fed, asset_fed, paiement_refill
):
    """
    Si Stripe dit `amount_total` different du Paiement_stripe local,
    le webhook retourne 400 et ne cree PAS de Transaction.
    Le paiement reste PENDING.
    """
    # Paiement local : 1500 cents. Stripe (mocke) annonce : 9999 cents.
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 9999  # tampering

    payload = _build_webhook_payload(paiement_refill, tenant_federation_fed, asset_uuid=asset_fed.uuid)
    request = RequestFactory().post("/webhook/stripe/")

    response = _process_stripe_webhook_cashless_refill(payload, request)

    assert response.status_code == 400

    assert not Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).exists()

    with tenant_context(tenant_federation_fed):
        paiement_refill.refresh_from_db()
        assert paiement_refill.status == Paiement_stripe.PENDING


def test_webhook_idempotent(
    mock_stripe, tenant_federation_fed, asset_fed, paiement_refill
):
    """
    Rejouer le meme webhook deux fois : une seule Transaction, Token credite
    une seule fois. Valide l'idempotence via select_for_update + check status=PAID.
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    payload = _build_webhook_payload(paiement_refill, tenant_federation_fed, asset_uuid=asset_fed.uuid)
    request = RequestFactory().post("/webhook/stripe/")

    response1 = _process_stripe_webhook_cashless_refill(payload, request)
    assert response1.status_code == 200

    response2 = _process_stripe_webhook_cashless_refill(payload, request)
    assert response2.status_code == 200

    assert Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).count() == 1


def test_webhook_reject_si_source_incorrecte(
    mock_stripe, tenant_federation_fed, asset_fed, paiement_refill
):
    """
    Si metadata.refill_type='FED' mais Paiement_stripe.source != CASHLESS_REFILL
    (cas forge par un attaquant), le webhook renvoie 400.
    """
    with tenant_context(tenant_federation_fed):
        paiement_refill.source = Paiement_stripe.API_BILLETTERIE
        paiement_refill.save(update_fields=["source"])

    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    payload = _build_webhook_payload(paiement_refill, tenant_federation_fed, asset_uuid=asset_fed.uuid)
    request = RequestFactory().post("/webhook/stripe/")

    response = _process_stripe_webhook_cashless_refill(payload, request)

    assert response.status_code == 400

    assert not Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).exists()
