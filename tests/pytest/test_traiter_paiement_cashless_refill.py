"""
Tests de la fonction commune traiter_paiement_cashless_refill.
Tests for the shared traiter_paiement_cashless_refill function.

LOCALISATION : tests/pytest/test_traiter_paiement_cashless_refill.py

Cette fonction vit dans ApiBillet/views.py et est appelee depuis :
- Le webhook Stripe (Webhook_stripe.post -> _process_stripe_webhook_cashless_refill)
- La vue de retour user (MyAccount.return_refill_wallet)

Elle garantit :
- Idempotence : un 2e appel apres paiement traite est un no-op
- Concurrency-safe : select_for_update serialise les appels concurrents
- Stripe API hors verrou : pas de lock DB tenu pendant l'appel reseau (1-3s)
- Anti-tampering : Stripe.amount_total == paiement.total()

Pattern inspire de Paiement_stripe.update_checkout_status() (billetterie /
adhesion) — meme convergence webhook + retour user.

/ This function is called from both Stripe webhook and user-return view.
Guarantees: idempotence, concurrency-safety, Stripe outside lock, anti-tampering.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_traiter_paiement_cashless_refill.py -v --api-key dummy
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
from fedow_core.models import Asset, Transaction, Token
from BaseBillet.models import Product, LigneArticle, PaymentMethod, Paiement_stripe
from ApiBillet.serializers import get_or_create_price_sold
from ApiBillet.views import (
    traiter_paiement_cashless_refill,
    CashlessRefillTamperingError,
)


TEST_PREFIX = "[test_traiter_refill]"


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
    Cree un Paiement_stripe CASHLESS_REFILL de 1500 cents (15 EUR),
    avec checkout_session_id_stripe match la fixture mock_stripe.
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
        pricesold = get_or_create_price_sold(price_refill, custom_amount=Decimal("15.00"))

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_traiter_nominal_cree_transaction_et_credite_token(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Nominal : Stripe dit paid + amount OK -> Transaction REFILL creee,
    Token credite, paiement.status = PAID.
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    request = RequestFactory().post("/")

    with tenant_context(tenant_federation_fed):
        result = traiter_paiement_cashless_refill(paiement_refill, request)

    assert result.status == Paiement_stripe.PAID

    # Une Transaction REFILL creee.
    tx = Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    )
    assert tx.count() == 1
    assert tx.first().amount == 1500

    # Token de l'user credite.
    asset_fed = Asset.objects.get(category=Asset.FED)
    token = Token.objects.get(wallet=paiement_refill.user.wallet, asset=asset_fed)
    assert token.value >= 1500  # >= car fixture partagee peut avoir du solde existant


def test_traiter_idempotent_sur_paiement_deja_paid(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Early return immediate si paiement.status == PAID (verifie sur l'objet
    fraichement charge depuis DB, comme en prod), sans appeler Stripe.

    Simule le scenario prod : webhook puis user qui revient — chacun recharge
    le paiement depuis la DB (requete distincte), donc voit le status a jour.
    / Simulates production: webhook + user-return — each reloads the paiement
    from DB (distinct requests), so each sees up-to-date status.
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    request = RequestFactory().post("/")

    # Premier appel : traite normalement, status passe a PAID en DB.
    with tenant_context(tenant_federation_fed):
        traiter_paiement_cashless_refill(paiement_refill, request)

    # Second appel : on RECHARGE le paiement depuis DB (comme le fait une
    # nouvelle requete HTTP en prod). Le status reflete alors PAID.
    with tenant_context(tenant_federation_fed):
        paiement_frais = Paiement_stripe.objects.get(uuid=paiement_refill.uuid)
        assert paiement_frais.status == Paiement_stripe.PAID

        calls_avant = mock_stripe.mock_retrieve.call_count
        result = traiter_paiement_cashless_refill(paiement_frais, request)
        calls_apres = mock_stripe.mock_retrieve.call_count

    # Early return prelim : Stripe.retrieve N'A PAS ete appele une 2e fois.
    # / Early return: Stripe.retrieve NOT called a 2nd time.
    assert calls_apres == calls_avant, (
        "Early return sur status=PAID (avant lock) doit court-circuiter Stripe"
    )

    # Toujours une seule Transaction REFILL.
    assert Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).count() == 1


def test_traiter_stripe_dit_pas_paye_pas_de_traitement(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Si Stripe dit payment_status != "paid" (SEPA pending, erreur transitoire),
    la fonction return sans rien faire. Paiement reste PENDING, pas de
    Transaction creee. Le webhook reessayera.
    """
    mock_stripe.session.payment_status = "unpaid"  # Stripe dit pas paye
    mock_stripe.session.amount_total = 1500

    request = RequestFactory().post("/")

    with tenant_context(tenant_federation_fed):
        result = traiter_paiement_cashless_refill(paiement_refill, request)

    # Status reste PENDING.
    assert result.status == Paiement_stripe.PENDING

    # Aucune Transaction creee.
    assert not Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).exists()


def test_traiter_tampering_leve_exception(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Si Stripe.amount_total != paiement.total() * 100, leve
    CashlessRefillTamperingError. Le paiement reste PENDING.
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 9999  # 99.99 EUR au lieu de 15 EUR

    request = RequestFactory().post("/")

    with tenant_context(tenant_federation_fed):
        with pytest.raises(CashlessRefillTamperingError):
            traiter_paiement_cashless_refill(paiement_refill, request)

        paiement_refill.refresh_from_db()
        assert paiement_refill.status == Paiement_stripe.PENDING

    # Aucune Transaction creee.
    assert not Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).exists()


def test_traiter_double_appel_webhook_puis_retour_user(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Simule le scenario realiste : webhook arrive, traite; user revient,
    fonction rappelee. Idempotent : 1 seule Transaction, Token credite 1x.

    Cas typique : c'est le scenario qu'on veut garantir en prod.
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    request = RequestFactory().post("/")

    asset_fed = Asset.objects.get(category=Asset.FED)

    # --- Appel 1 : webhook arrive ---
    with tenant_context(tenant_federation_fed):
        traiter_paiement_cashless_refill(paiement_refill, request)

    token_apres_1 = Token.objects.get(
        wallet=paiement_refill.user.wallet, asset=asset_fed
    ).value
    count_apres_1 = Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).count()

    # --- Appel 2 : user revient, meme paiement ---
    with tenant_context(tenant_federation_fed):
        # refresh_from_db pour simuler une nouvelle requete (nouveau chargement)
        paiement_refill.refresh_from_db()
        traiter_paiement_cashless_refill(paiement_refill, request)

    token_apres_2 = Token.objects.get(
        wallet=paiement_refill.user.wallet, asset=asset_fed
    ).value
    count_apres_2 = Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).count()

    # Token pas credite 2x.
    assert token_apres_2 == token_apres_1, (
        f"Token credite une 2e fois : {token_apres_1} -> {token_apres_2}"
    )

    # Toujours une seule Transaction.
    assert count_apres_2 == count_apres_1 == 1


def test_traiter_xff_multi_ip_derriere_chaine_proxies(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    HTTP_X_FORWARDED_FOR peut contenir plusieurs IPs separees par ", "
    derriere une chaine de proxies (Traefik + Docker + ...). La fonction
    doit extraire la premiere (IP du client original) pour
    GenericIPAddressField, pas passer la liste brute (qui leve ValueError).

    Regression test pour l'erreur rencontree en prod :
    "'172.21.0.1, 172.21.0.2' does not appear to be an IPv4 or IPv6 address"
    """
    mock_stripe.session.payment_status = "paid"
    mock_stripe.session.amount_total = 1500

    # Simule une chaine de proxies (Traefik -> Daphne).
    # / Simulates a proxy chain (Traefik -> Daphne).
    request = RequestFactory().post(
        "/",
        HTTP_X_FORWARDED_FOR="172.21.0.1, 172.21.0.2",
    )

    with tenant_context(tenant_federation_fed):
        result = traiter_paiement_cashless_refill(paiement_refill, request)

    # Paiement traite correctement.
    assert result.status == Paiement_stripe.PAID

    # Transaction creee avec la 1re IP (client original).
    tx = Transaction.objects.get(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    )
    assert tx.ip == "172.21.0.1"


def test_traiter_stripe_api_fail_ne_crash_pas(
    mock_stripe, tenant_federation_fed, paiement_refill
):
    """
    Si Stripe.retrieve leve une exception (timeout reseau, cle invalide),
    la fonction log un warning et return sans modifier le paiement.
    Ne doit pas faire planter l'appelant (webhook ou vue retour).
    """
    # Force Stripe.retrieve a lever une exception.
    mock_stripe.mock_retrieve.side_effect = Exception("Stripe API timeout")

    request = RequestFactory().post("/")

    with tenant_context(tenant_federation_fed):
        result = traiter_paiement_cashless_refill(paiement_refill, request)

    # Paiement inchange.
    assert result.status == Paiement_stripe.PENDING

    # Pas de Transaction.
    assert not Transaction.objects.filter(
        checkout_stripe=paiement_refill.uuid,
        action=Transaction.REFILL,
    ).exists()

    # Reset le mock pour les tests suivants.
    mock_stripe.mock_retrieve.side_effect = None
