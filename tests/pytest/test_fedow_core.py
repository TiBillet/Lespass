"""
tests/pytest/test_fedow_core.py — Tests unitaires fedow_core (Phase 0).
tests/pytest/test_fedow_core.py — Unit tests for fedow_core (Phase 0).

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_fedow_core.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# Ajouter ce chemin pour que Python trouve le module TiBillet.settings.
# Django code is in /DjangoFiles inside the container.
# Add this path so Python can find the TiBillet.settings module.
sys.path.insert(0, '/DjangoFiles')


import django

django.setup()

import pytest

from django.db import transaction
from django.db.models import Q

from Customers.models import Client
from AuthBillet.models import Wallet
from fedow_core.exceptions import SoldeInsuffisant
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, TransactionService, WalletService

# Prefixe pour identifier les donnees de test et les nettoyer.
# Prefix to identify test data and clean it up.
TEST_PREFIX = '[test_fedow_core]'


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
def wallet_lieu_b():
    return Wallet.objects.create(name=f'{TEST_PREFIX} Lieu B')


@pytest.fixture(scope="module")
def asset_monnaie_locale(tenant_a, wallet_bar):
    return AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Monnaie locale',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_bar,
    )


@pytest.fixture(scope="module")
def asset_tenant_b(tenant_b, wallet_lieu_b):
    return AssetService.creer_asset(
        tenant=tenant_b,
        name=f'{TEST_PREFIX} Fidelite B',
        category=Asset.FID,
        currency_code='PTS',
        wallet_origin=wallet_lieu_b,
    )


# ---------------------------------------------------------------------------
# Nettoyage en fin de module
# Cleanup at end of module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """
    Supprime toutes les donnees creees par ce module de test.
    Deletes all data created by this test module.
    Ordre : Transactions → Tokens → Assets → Wallets (respect des FK PROTECT).
    Order: Transactions → Tokens → Assets → Wallets (respect FK PROTECT).
    """
    yield

    # Les transactions referencent les assets et wallets (PROTECT).
    # Il faut les supprimer en premier.
    # Transactions reference assets and wallets (PROTECT).
    # They must be deleted first.
    #
    # Le try/except attrape les erreurs de tables tenant manquantes
    # (ex: BaseBillet_lignearticle) quand les tests tournent sur le schema public.
    # The try/except catches missing tenant table errors
    # (e.g. BaseBillet_lignearticle) when tests run on the public schema.
    try:
        wallets_de_test = Wallet.objects.filter(name__startswith=TEST_PREFIX)
        assets_de_test = Asset.objects.filter(name__startswith=TEST_PREFIX)

        Transaction.objects.filter(asset__in=assets_de_test).delete()
        Token.objects.filter(wallet__in=wallets_de_test).delete()
        assets_de_test.delete()
        wallets_de_test.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test 1 : creer Asset, Wallet, Token, crediter, verifier value
# Test 1: create Asset, Wallet, Token, credit, verify value
# ---------------------------------------------------------------------------

def test_fedow_core_base(tenant_a, wallet_alice, wallet_bar, asset_monnaie_locale):
    assert asset_monnaie_locale.category == Asset.TLF
    assert asset_monnaie_locale.tenant_origin == tenant_a

    # Solde initial = 0 (pas de Token).
    # Initial balance = 0 (no Token).
    solde_initial = WalletService.obtenir_solde(wallet=wallet_alice, asset=asset_monnaie_locale)
    assert solde_initial == 0

    # Crediter 10,00 EUR (1000 centimes).
    # Credit 10.00 EUR (1000 cents).
    with transaction.atomic():
        WalletService.crediter(wallet=wallet_alice, asset=asset_monnaie_locale, montant_en_centimes=1000)

    token = Token.objects.get(wallet=wallet_alice, asset=asset_monnaie_locale)
    assert token.value == 1000


# ---------------------------------------------------------------------------
# Test 2 : id auto-increment (BigAutoField)
# Test 2: id auto-increment (BigAutoField)
# ---------------------------------------------------------------------------

def test_id_auto_increment(tenant_a, wallet_alice, wallet_bar, asset_monnaie_locale):
    # Crediter assez pour 2 ventes.
    # Credit enough for 2 sales.
    with transaction.atomic():
        WalletService.crediter(wallet=wallet_alice, asset=asset_monnaie_locale, montant_en_centimes=2000)

    tx1 = TransactionService.creer_vente(
        sender_wallet=wallet_alice, receiver_wallet=wallet_bar,
        asset=asset_monnaie_locale, montant_en_centimes=100, tenant=tenant_a,
    )
    tx2 = TransactionService.creer_vente(
        sender_wallet=wallet_alice, receiver_wallet=wallet_bar,
        asset=asset_monnaie_locale, montant_en_centimes=200, tenant=tenant_a,
    )

    # BigAutoField : l'id est attribue automatiquement par Django/PostgreSQL.
    # Pas besoin de refresh_from_db(), Django le remplit directement apres create().
    # BigAutoField: id is assigned automatically by Django/PostgreSQL.
    # No need for refresh_from_db(), Django fills it directly after create().
    assert tx1.id is not None
    assert tx2.id is not None
    assert tx2.id > tx1.id


# ---------------------------------------------------------------------------
# Test 3 : SoldeInsuffisant
# Test 3: SoldeInsuffisant
# ---------------------------------------------------------------------------

def test_solde_insuffisant(asset_monnaie_locale):
    wallet_vide = Wallet.objects.create(name=f'{TEST_PREFIX} Wallet vide')

    with pytest.raises(SoldeInsuffisant) as exc_info:
        with transaction.atomic():
            WalletService.debiter(wallet=wallet_vide, asset=asset_monnaie_locale, montant_en_centimes=100)

    assert exc_info.value.solde_actuel_en_centimes == 0
    assert exc_info.value.montant_demande_en_centimes == 100


# ---------------------------------------------------------------------------
# Test 4 : pas de leak cross-tenant
# Test 4: no cross-tenant leak
# ---------------------------------------------------------------------------

def test_pas_de_leak_cross_tenant(tenant_a, tenant_b, asset_monnaie_locale, asset_tenant_b):
    # Asset.objects.all() retourne TOUT (SHARED_APPS = pas de filtre auto).
    # Asset.objects.all() returns ALL (SHARED_APPS = no automatic filter).
    tous_les_uuids = list(Asset.objects.values_list('uuid', flat=True))
    assert asset_monnaie_locale.uuid in tous_les_uuids
    assert asset_tenant_b.uuid in tous_les_uuids

    # Le service filtre par tenant.
    # The service filters by tenant.
    uuids_tenant_a = list(AssetService.obtenir_assets_du_tenant(tenant_a).values_list('uuid', flat=True))
    assert asset_monnaie_locale.uuid in uuids_tenant_a
    assert asset_tenant_b.uuid not in uuids_tenant_a

    uuids_tenant_b = list(AssetService.obtenir_assets_du_tenant(tenant_b).values_list('uuid', flat=True))
    assert asset_tenant_b.uuid in uuids_tenant_b
    assert asset_monnaie_locale.uuid not in uuids_tenant_b


# ---------------------------------------------------------------------------
# Test 5 : Transaction porte le bon tenant
# Test 5: Transaction carries the correct tenant
# ---------------------------------------------------------------------------

def test_transaction_porte_le_bon_tenant(tenant_a, wallet_alice, wallet_bar, asset_monnaie_locale):
    with transaction.atomic():
        WalletService.crediter(wallet=wallet_alice, asset=asset_monnaie_locale, montant_en_centimes=500)

    tx = TransactionService.creer_vente(
        sender_wallet=wallet_alice, receiver_wallet=wallet_bar,
        asset=asset_monnaie_locale, montant_en_centimes=100, tenant=tenant_a,
    )

    assert tx.tenant == tenant_a

    # Relire depuis la base pour confirmer.
    # Re-read from database to confirm.
    tx_relue = Transaction.objects.get(uuid=tx.uuid)
    assert tx_relue.tenant_id == tenant_a.pk


# ---------------------------------------------------------------------------
# Test 6 : pending_invitations — un lieu invite voit l'invitation
# Test 6: pending_invitations — an invited venue sees the invitation
# ---------------------------------------------------------------------------

def test_asset_pending_invitations(tenant_a, tenant_b, wallet_bar):
    # Creer un asset pour ce test.
    # Create an asset for this test.
    asset = AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Asset invitation test',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_bar,
    )

    # Inviter tenant_b a partager cet asset.
    # Invite tenant_b to share this asset.
    asset.pending_invitations.add(tenant_b)

    # Verifier que tenant_b est dans pending_invitations.
    # Check that tenant_b is in pending_invitations.
    assert asset.pending_invitations.filter(pk=tenant_b.pk).exists()

    # Verifier que tenant_b n'est PAS dans federated_with.
    # Check that tenant_b is NOT in federated_with.
    assert not asset.federated_with.filter(pk=tenant_b.pk).exists()


# ---------------------------------------------------------------------------
# Test 7 : accepter une invitation — deplacement pending → federated
# Test 7: accept invitation — move from pending → federated
# ---------------------------------------------------------------------------

def test_asset_accept_invitation(tenant_a, tenant_b, wallet_bar):
    # Creer un asset et inviter tenant_b.
    # Create an asset and invite tenant_b.
    asset = AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Asset accept test',
        category=Asset.TNF,
        currency_code='PTS',
        wallet_origin=wallet_bar,
    )
    asset.pending_invitations.add(tenant_b)

    # Simuler ce que fait accept_asset_invitation :
    # deplacer de pending_invitations vers federated_with.
    # Simulate what accept_asset_invitation does:
    # move from pending_invitations to federated_with.
    asset.pending_invitations.remove(tenant_b)
    asset.federated_with.add(tenant_b)

    # Relire depuis la base pour confirmer.
    # Re-read from database to confirm.
    asset.refresh_from_db()

    # tenant_b ne doit plus etre dans pending_invitations.
    # tenant_b must no longer be in pending_invitations.
    assert not asset.pending_invitations.filter(pk=tenant_b.pk).exists()

    # tenant_b doit etre dans federated_with.
    # tenant_b must be in federated_with.
    assert asset.federated_with.filter(pk=tenant_b.pk).exists()


# ---------------------------------------------------------------------------
# Test 8 : visibilite — le queryset admin montre les assets federes
# Test 8: visibility — admin queryset shows federated assets
# ---------------------------------------------------------------------------

def test_asset_visible_pour_lieu_federe(tenant_a, tenant_b, wallet_bar):
    # Creer un asset par tenant_a, federe avec tenant_b.
    # Create an asset by tenant_a, federated with tenant_b.
    asset = AssetService.creer_asset(
        tenant=tenant_a,
        name=f'{TEST_PREFIX} Asset visibilite test',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_bar,
    )
    asset.federated_with.add(tenant_b)

    # Simuler le queryset admin :
    # Q(tenant_origin=tenant) | Q(federated_with=tenant)
    # Simulate the admin queryset:
    # Q(tenant_origin=tenant) | Q(federated_with=tenant)

    # tenant_a (createur) voit l'asset.
    # tenant_a (creator) sees the asset.
    qs_tenant_a = Asset.objects.filter(
        Q(tenant_origin=tenant_a) | Q(federated_with=tenant_a)
    ).distinct()
    assert qs_tenant_a.filter(pk=asset.pk).exists()

    # tenant_b (federe) voit l'asset.
    # tenant_b (federated) sees the asset.
    qs_tenant_b = Asset.objects.filter(
        Q(tenant_origin=tenant_b) | Q(federated_with=tenant_b)
    ).distinct()
    assert qs_tenant_b.filter(pk=asset.pk).exists()

    # Un autre tenant (schema_name different) ne verrait pas l'asset.
    # Another tenant (different schema_name) would not see the asset.
    #
    # On utilise un UUID inexistant pour simuler un tenant_c.
    # We use a non-existent UUID to simulate a tenant_c.
    import uuid as uuid_mod
    tenant_c_pk = uuid_mod.uuid4()
    qs_tenant_c = Asset.objects.filter(
        Q(tenant_origin_id=tenant_c_pk) | Q(federated_with__pk=tenant_c_pk)
    ).distinct()
    assert not qs_tenant_c.filter(pk=asset.pk).exists()
