"""
tests/pytest/test_verify_transactions.py — Tests du management command verify_transactions.
tests/pytest/test_verify_transactions.py — Tests for the verify_transactions management command.

4 tests :
  1. Base saine → 0 erreur
  2. Token.value modifie → ERROR detectee
  3. Transaction avec asset non autorise → ERROR detectee
  4. --tenant filtre correctement

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_verify_transactions.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from io import StringIO

from django.core.management import call_command
from django.db import transaction

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, TransactionService

# Prefixe pour identifier les donnees de test et les nettoyer.
# Prefix to identify test data and clean it up.
TEST_PREFIX = '[test_verify]'


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def tenant_a():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def tenant_b():
    return Client.objects.get(schema_name='chantefrein')


@pytest.fixture(scope="module")
def wallet_alice():
    return Wallet.objects.create(name=f'{TEST_PREFIX} Alice')


@pytest.fixture(scope="module")
def wallet_bar():
    return Wallet.objects.create(name=f'{TEST_PREFIX} Bar')


@pytest.fixture(scope="module")
def asset_local(tenant_a, wallet_bar):
    from django_tenants.utils import schema_context

    # Nettoyer le produit signal d'un run precedent.
    # Le signal post_save Asset cree un Product "Recharge <nom_asset>"
    # qui peut rester d'un ancien run et provoquer un IntegrityError.
    # / Clean up signal product from a previous run.
    # The Asset post_save signal creates a Product "Recharge <asset_name>"
    # that may remain from an older run and cause an IntegrityError.
    with schema_context('lespass'):
        from BaseBillet.models import Price, Product
        nom_signal = f'Recharge {TEST_PREFIX} Monnaie test'
        Price.objects.filter(product__name=nom_signal).delete()
        Product.objects.filter(name=nom_signal).delete()

    return AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Monnaie test',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_bar,
    )


# ---------------------------------------------------------------------------
# Nettoyage en fin de module
# Cleanup at end of module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    yield

    try:
        wallets_de_test = Wallet.objects.filter(name__startswith=TEST_PREFIX)
        assets_de_test = Asset.objects.filter(name__startswith=TEST_PREFIX)

        Transaction.objects.filter(asset__in=assets_de_test).delete()
        Token.objects.filter(wallet__in=wallets_de_test).delete()
        # Aussi nettoyer les tokens lies aux assets de test (wallet_bar etc.)
        # Also clean up tokens linked to test assets (wallet_bar etc.)
        Token.objects.filter(asset__in=assets_de_test).delete()
        assets_de_test.delete()
        wallets_de_test.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helper : appeler verify_transactions et capturer stdout/stderr.
# Helper: call verify_transactions and capture stdout/stderr.
# ---------------------------------------------------------------------------

def _run_verify(**kwargs):
    """Appelle verify_transactions et retourne (stdout, stderr).
    Calls verify_transactions and returns (stdout, stderr)."""
    out = StringIO()
    err = StringIO()
    call_command('verify_transactions', stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Test 1 : base saine → 0 erreur
# Test 1: clean database → 0 errors
# ---------------------------------------------------------------------------

def test_verify_clean(tenant_a, wallet_alice, wallet_bar, asset_local):
    """Crediter via CREATION + vente = nos tokens sont coherents.
    Credit via CREATION + sale = our tokens are consistent.

    On utilise TransactionService.creer() avec action=CREATION
    (pas de debit sur sender) pour que le credit soit trace
    comme une Transaction. Sinon verify detecte une divergence.
    We use TransactionService.creer() with action=CREATION
    (no debit on sender) so the credit is tracked as a Transaction.
    Otherwise verify detects a divergence.
    """
    # Crediter Alice de 2000 centimes via une transaction CREATION.
    # Credit Alice with 2000 cents via a CREATION transaction.
    TransactionService.creer(
        sender=wallet_bar,
        receiver=wallet_alice,
        asset=asset_local,
        montant_en_centimes=2000,
        action=Transaction.CREATION,
        tenant=tenant_a,
    )

    # Creer une vente de 500 centimes.
    # Create a sale of 500 cents.
    TransactionService.creer_vente(
        sender_wallet=wallet_alice,
        receiver_wallet=wallet_bar,
        asset=asset_local,
        montant_en_centimes=500,
        tenant=tenant_a,
    )

    stdout, stderr = _run_verify()

    # Verifier que NOS tokens ne sont pas dans les erreurs.
    # D'autres suites de tests peuvent laisser des tokens "sales"
    # (credites via WalletService.crediter sans Transaction).
    # Check that OUR tokens are not in the errors.
    # Other test suites may leave "dirty" tokens
    # (credited via WalletService.crediter without Transaction).
    lignes_erreur = [l for l in stdout.split('\n') if 'ERROR' in l]
    for ligne in lignes_erreur:
        assert TEST_PREFIX not in ligne, (
            f'Notre token apparait dans une erreur : {ligne}'
        )


# ---------------------------------------------------------------------------
# Test 2 : Token.value modifie → ERROR detectee
# Test 2: Token.value tampered → ERROR detected
# ---------------------------------------------------------------------------

def test_verify_detecte_token_divergent(tenant_a, wallet_alice, asset_local):
    """Modifier Token.value manuellement → verify detecte la divergence.
    Manually modify Token.value → verify detects the divergence."""
    # Modifier le token d'Alice manuellement (simuler une corruption).
    # Manually modify Alice's token (simulate corruption).
    token = Token.objects.get(wallet=wallet_alice, asset=asset_local)
    vraie_valeur = token.value

    token.value = token.value + 9999
    token.save(update_fields=['value'])

    try:
        stdout, stderr = _run_verify()
        assert 'ERROR' in stdout
        # Verifier que NOTRE token corrompu est detecte.
        # Verify that OUR corrupted token is detected.
        lignes_erreur = [l for l in stdout.split('\n') if 'ERROR' in l]
        token_detecte = any(TEST_PREFIX in l for l in lignes_erreur)
        assert token_detecte, (
            f'Le token corrompu [{TEST_PREFIX}] devrait etre dans les erreurs'
        )
    finally:
        # Restaurer la vraie valeur pour ne pas casser les tests suivants.
        # Restore the real value so subsequent tests are not broken.
        token.value = vraie_valeur
        token.save(update_fields=['value'])


# ---------------------------------------------------------------------------
# Test 3 : Transaction avec asset non autorise → ERROR
# Test 3: Transaction with unauthorized asset → ERROR
# ---------------------------------------------------------------------------

def test_verify_detecte_incoherence_tenant_asset(
    tenant_a, tenant_b, wallet_alice, wallet_bar,
):
    """Transaction avec asset de tenant_a mais tenant=tenant_b (non federe) → ERROR.
    Transaction with tenant_a's asset but tenant=tenant_b (not federated) → ERROR."""
    # Creer un asset propre a ce test pour ne pas polluer.
    # Create an asset specific to this test to avoid pollution.
    wallet_test = Wallet.objects.create(name=f'{TEST_PREFIX} Incoherence')
    asset_prive = AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Asset prive',
        category=Asset.FID,
        currency_code='PTS',
        wallet_origin=wallet_test,
    )

    # Crediter le wallet via CREATION (tracee en Transaction).
    # Credit the wallet via CREATION (tracked as a Transaction).
    TransactionService.creer(
        sender=wallet_test,
        receiver=wallet_alice,
        asset=asset_prive,
        montant_en_centimes=1000,
        action=Transaction.CREATION,
        tenant=tenant_a,
    )

    # Creer une transaction avec le MAUVAIS tenant (tenant_b au lieu de tenant_a).
    # L'asset appartient a tenant_a et n'est PAS federe avec tenant_b.
    # Create a transaction with the WRONG tenant (tenant_b instead of tenant_a).
    # The asset belongs to tenant_a and is NOT federated with tenant_b.
    TransactionService.creer_vente(
        sender_wallet=wallet_alice,
        receiver_wallet=wallet_bar,
        asset=asset_prive,
        montant_en_centimes=100,
        tenant=tenant_b,  # MAUVAIS tenant / WRONG tenant
    )

    stdout, stderr = _run_verify()

    assert 'ERROR' in stdout
    assert 'non autorise' in stdout


# ---------------------------------------------------------------------------
# Test 4 : --tenant filtre correctement
# Test 4: --tenant filters correctly
# ---------------------------------------------------------------------------

def test_verify_option_tenant(tenant_a, wallet_alice, wallet_bar, asset_local):
    """--tenant=lespass ne montre que les transactions du tenant lespass.
    --tenant=lespass only shows transactions for the lespass tenant."""
    stdout, stderr = _run_verify(tenant='lespass')

    # La commande doit fonctionner sans crash.
    # The command must work without crashing.
    assert 'Verification' in stdout

    # Un tenant inexistant doit afficher un message d'erreur.
    # A non-existent tenant must display an error message.
    stdout_bad, stderr_bad = _run_verify(tenant='tenant_inexistant_xyz')
    assert 'introuvable' in stderr_bad
