"""
tests/pytest/test_paiement_cashless.py — Tests Phase 3 etape 1 : paiement NFC cashless.
tests/pytest/test_paiement_cashless.py — Tests Phase 3 step 1: NFC cashless payment.

Couvre : _payer_par_nfc, Transaction fedow_core, Token debit/credit,
         LigneArticle avec champs NFC, atomicite, rollback.
Covers: _payer_par_nfc, fedow_core Transaction, Token debit/credit,
        LigneArticle with NFC fields, atomicity, rollback.

IMPORTANT : ces tests sont conçus pour fonctionner quand d'autres suites
(test_fedow_core.py) ont deja cree des assets TLF pour le meme tenant.
La vue utilise Asset.objects.filter(...).first(), donc on nettoie les TLF
parasites en debut de module pour garantir l'isolation.

IMPORTANT: these tests are designed to work when other suites
(test_fedow_core.py) have already created TLF assets for the same tenant.
The view uses Asset.objects.filter(...).first(), so we clean up stale TLF
assets at module start to guarantee isolation.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_paiement_cashless.py -v --api-key dummy
"""

import os
import sys

# Le code Django est dans /DjangoFiles a l'interieur du conteneur.
# / Django code is in /DjangoFiles inside the container.
sys.path.insert(0, '/DjangoFiles')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django

django.setup()

import pytest

from unittest.mock import patch

from django.db import connection
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    LigneArticle, PaymentMethod, Price, Product,
    ProductSold, PriceSold, SaleOrigin,
)
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, WalletService
from laboutik.models import PointDeVente


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
    """Un utilisateur admin du tenant avec un wallet.
    / A tenant admin user with a wallet."""
    with schema_context(TENANT_SCHEMA):
        email = 'admin-test-cashless@tibillet.localhost'
        user, created = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        # S'assurer que l'admin a un wallet
        # / Ensure admin has a wallet
        if not user.wallet:
            user.wallet = Wallet.objects.create(name='[test_cashless] Admin')
            user.save(update_fields=['wallet'])
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


@pytest.fixture(scope="module")
def wallet_lieu():
    """Wallet du lieu pour recevoir les paiements.
    / Venue wallet to receive payments."""
    return Wallet.objects.create(name='[test_cashless] Lieu')


@pytest.fixture(scope="module")
def asset_tlf(tenant, wallet_lieu):
    """Asset TLF (monnaie locale euro) du tenant.
    / TLF asset (local fiat currency) for the tenant.

    Desactive les eventuels autres TLF du meme tenant (crees par
    d'autres suites de tests comme test_fedow_core) pour que
    Asset.objects.filter(..., active=True).first() retourne celui-ci.

    Deactivates any other TLF assets for this tenant (created by
    other test suites like test_fedow_core) so that
    Asset.objects.filter(..., active=True).first() returns this one.
    """
    # Desactiver les autres TLF actifs du tenant pour eviter l'ambiguite
    # / Deactivate other active TLF assets for this tenant to avoid ambiguity
    Asset.objects.filter(
        tenant_origin=tenant,
        category=Asset.TLF,
        active=True,
    ).update(active=False)

    asset = AssetService.creer_asset(
        tenant=tenant,
        name='TestCoin Cashless',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_lieu,
    )
    return asset


@pytest.fixture(scope="module")
def wallet_client():
    """Wallet pour le client NFC (carte avec user).
    / Wallet for the NFC client (card with user)."""
    return Wallet.objects.create(name='[test_cashless] Client')


@pytest.fixture(scope="module")
def carte_client_avec_user(wallet_client):
    """CarteCashless liee a un TibilletUser avec wallet.
    / CarteCashless linked to a TibilletUser with wallet."""
    email = 'client-nfc-test@tibillet.localhost'
    user, _ = TibilletUser.objects.get_or_create(
        email=email,
        defaults={
            'username': email,
            'is_active': True,
        },
    )
    # Toujours mettre a jour le wallet (il peut avoir change entre les runs)
    # / Always update wallet (it may have changed between runs)
    user.wallet = wallet_client
    user.save(update_fields=['wallet'])

    carte, _ = CarteCashless.objects.get_or_create(
        tag_id='NFCTEST1',
        defaults={
            'number': 'NFCNUM01',
            'uuid': None,
            'user': user,
        },
    )
    # S'assurer que la carte est liee au bon user
    # / Ensure the card is linked to the correct user
    if carte.user != user:
        carte.user = user
        carte.save(update_fields=['user'])
    return carte


@pytest.fixture(scope="module")
def wallet_ephemere():
    """Wallet ephemere pour carte anonyme.
    / Ephemeral wallet for anonymous card."""
    return Wallet.objects.create(name='[test_cashless] Ephemere')


@pytest.fixture(scope="module")
def carte_anonyme(wallet_ephemere):
    """CarteCashless anonyme (sans user, avec wallet_ephemere).
    / Anonymous CarteCashless (no user, with wallet_ephemere)."""
    carte, _ = CarteCashless.objects.get_or_create(
        tag_id='NFCTEST2',
        defaults={
            'number': 'NFCNUM02',
            'uuid': None,
            'wallet_ephemere': wallet_ephemere,
        },
    )
    if carte.wallet_ephemere != wallet_ephemere:
        carte.wallet_ephemere = wallet_ephemere
        carte.save(update_fields=['wallet_ephemere'])
    return carte


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crediter_wallet(wallet, asset, montant_centimes):
    """Credite un wallet avec un montant en centimes (dans un bloc atomic).
    / Credits a wallet with an amount in cents (inside an atomic block)."""
    from django.db import transaction as db_transaction
    with db_transaction.atomic():
        WalletService.crediter(
            wallet=wallet,
            asset=asset,
            montant_en_centimes=montant_centimes,
        )


def _make_client(admin_user, tenant):
    """Cree un client DRF authentifie comme admin du tenant.
    / Creates a DRF client authenticated as tenant admin."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults['SERVER_NAME'] = f'{TENANT_SCHEMA}.tibillet.localhost'
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestPaiementNFCAtomique:
    """Test 1 : paiement NFC avec solde suffisant.
    / Test 1: NFC payment with sufficient balance."""

    def test_paiement_nfc_atomique(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf, wallet_client, carte_client_avec_user,
    ):
        """Payer par NFC cree Transaction + Token debite + LigneArticle(LE).
        / NFC payment creates Transaction + Token debited + LigneArticle(LE)."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet client avec assez pour payer
            # / Credit client wallet with enough to pay
            _crediter_wallet(wallet_client, asset_tlf, 5000)

            solde_avant = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)

            # Filtrer par card pour isoler des autres tests
            # / Filter by card to isolate from other tests
            nb_transactions_avant = Transaction.objects.filter(
                tenant=tenant, action=Transaction.SALE,
                card=carte_client_avec_user,
            ).count()
            nb_lignes_avant = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                payment_method=PaymentMethod.LOCAL_EURO,
                carte=carte_client_avec_user,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client_avec_user.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier que la reponse est bien un succes (pas un message d'erreur)
            # / Verify the response is a success (not an error message)
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok' dans la reponse, obtenu : {contenu[:200]}"
            )

            # Verifier : Transaction SALE creee pour cette carte
            # / Verify: SALE Transaction created for this card
            nb_transactions_apres = Transaction.objects.filter(
                tenant=tenant, action=Transaction.SALE,
                card=carte_client_avec_user,
            ).count()
            assert nb_transactions_apres == nb_transactions_avant + 1

            # Verifier : Token debite du bon montant
            # / Verify: Token debited by the correct amount
            solde_apres = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
            assert solde_apres == solde_avant - prix_centimes

            # Verifier : LigneArticle avec payment_method=LOCAL_EURO pour cette carte
            # / Verify: LigneArticle with payment_method=LOCAL_EURO for this card
            nb_lignes_apres = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                payment_method=PaymentMethod.LOCAL_EURO,
                carte=carte_client_avec_user,
            ).count()
            assert nb_lignes_apres == nb_lignes_avant + 1


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCRollbackSoldeInsuffisant:
    """Test 2 : solde insuffisant → rien ne change en DB.
    / Test 2: insufficient balance → nothing changes in DB."""

    def test_paiement_nfc_rollback_solde_insuffisant(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf,
    ):
        """Wallet avec solde < total → Token inchange, 0 Transaction, 0 LigneArticle.
        / Wallet with balance < total → Token unchanged, 0 Transaction, 0 LigneArticle."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            # Creer un wallet client avec solde insuffisant
            # / Create a client wallet with insufficient balance
            wallet_pauvre = Wallet.objects.create(name='[test_cashless] Pauvre')
            _crediter_wallet(wallet_pauvre, asset_tlf, 1)  # 1 centime seulement

            user_pauvre, _ = TibilletUser.objects.get_or_create(
                email='pauvre-nfc@tibillet.localhost',
                defaults={'username': 'pauvre-nfc@tibillet.localhost', 'is_active': True},
            )
            user_pauvre.wallet = wallet_pauvre
            user_pauvre.save(update_fields=['wallet'])

            carte_pauvre, _ = CarteCashless.objects.get_or_create(
                tag_id='NFCPOOR1',
                defaults={'number': 'NFCNMP01', 'uuid': None, 'user': user_pauvre},
            )

            solde_avant = WalletService.obtenir_solde(wallet=wallet_pauvre, asset=asset_tlf)
            nb_transactions_avant = Transaction.objects.filter(
                tenant=tenant, card=carte_pauvre,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_pauvre.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier que la reponse est "fonds insuffisants"
            # / Verify response is "insufficient funds"
            contenu = response.content.decode()
            assert "insuffisants" in contenu.lower() or "Il manque" in contenu

            # Verifier : rien n'a change
            # / Verify: nothing changed
            solde_apres = WalletService.obtenir_solde(wallet=wallet_pauvre, asset=asset_tlf)
            assert solde_apres == solde_avant

            nb_transactions_apres = Transaction.objects.filter(
                tenant=tenant, card=carte_pauvre,
            ).count()
            assert nb_transactions_apres == nb_transactions_avant


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCCarteInconnue:
    """Test 3 : carte inconnue → message d'erreur, rien en DB.
    / Test 3: unknown card → error message, nothing in DB."""

    def test_paiement_nfc_carte_inconnue(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
    ):
        """tag_id='ZZZZZZZZ' → 'Carte inconnue', rien en DB.
        / tag_id='ZZZZZZZZ' → 'Carte inconnue', nothing in DB."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            nb_transactions_avant = Transaction.objects.filter(tenant=tenant).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': 'ZZZZZZZZ',
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Carte inconnue" in contenu

            # Rien en DB
            # / Nothing in DB
            nb_transactions_apres = Transaction.objects.filter(tenant=tenant).count()
            assert nb_transactions_apres == nb_transactions_avant


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCWalletEphemere:
    """Test 4 : paiement via wallet ephemere (carte anonyme).
    / Test 4: payment via ephemeral wallet (anonymous card)."""

    def test_paiement_nfc_wallet_ephemere(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf, wallet_ephemere, carte_anonyme,
    ):
        """Carte anonyme avec wallet_ephemere → Token debite sur wallet_ephemere.
        / Anonymous card with wallet_ephemere → Token debited on wallet_ephemere."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet ephemere
            # / Credit the ephemeral wallet
            _crediter_wallet(wallet_ephemere, asset_tlf, 5000)

            solde_avant = WalletService.obtenir_solde(wallet=wallet_ephemere, asset=asset_tlf)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_anonyme.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier que la reponse est bien un succes
            # / Verify the response is a success
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok', obtenu : {contenu[:200]}"
            )

            # Verifier : Token debite sur wallet_ephemere
            # / Verify: Token debited on wallet_ephemere
            solde_apres = WalletService.obtenir_solde(wallet=wallet_ephemere, asset=asset_tlf)
            assert solde_apres == solde_avant - prix_centimes


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCProductSoldPriceSold:
    """Test 5 : paiement NFC cree ProductSold et PriceSold.
    / Test 5: NFC payment creates ProductSold and PriceSold."""

    def test_paiement_nfc_cree_pricesold_productsold(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf, wallet_client, carte_client_avec_user,
    ):
        """LigneArticle.pricesold.productsold.product == bon Product.
        / LigneArticle.pricesold.productsold.product == correct Product."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            # S'assurer qu'il y a assez de solde
            # / Ensure there's enough balance
            _crediter_wallet(wallet_client, asset_tlf, 5000)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client_avec_user.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Verifier la chaine LigneArticle → PriceSold → ProductSold → Product
            # / Verify the chain LigneArticle → PriceSold → ProductSold → Product
            derniere_ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                payment_method=PaymentMethod.LOCAL_EURO,
                carte=carte_client_avec_user,
            ).order_by('-datetime').first()

            assert derniere_ligne is not None
            assert derniere_ligne.pricesold.productsold.product == produit


@pytest.mark.usefixtures("test_data")
class TestPaiementNFCTenantSurTransaction:
    """Test 6 : Transaction.tenant == le bon tenant.
    / Test 6: Transaction.tenant == correct tenant."""

    def test_paiement_nfc_tenant_sur_transaction(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf, wallet_client, carte_client_avec_user,
    ):
        """Transaction creee a bien tenant == connection.tenant.
        / Created Transaction has tenant == connection.tenant."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            _crediter_wallet(wallet_client, asset_tlf, 5000)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client_avec_user.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Chercher la derniere transaction SALE de cette carte
            # / Find the last SALE transaction for this card
            derniere_transaction = Transaction.objects.filter(
                action=Transaction.SALE,
                card=carte_client_avec_user,
            ).order_by('-id').first()

            assert derniere_transaction is not None
            assert derniere_transaction.tenant == tenant


@pytest.mark.usefixtures("test_data")
class TestAtomiciteSiErreurLigneArticle:
    """Test 7 : si LigneArticle.create echoue, Token revient.
    / Test 7: if LigneArticle.create fails, Token reverts."""

    def test_atomicite_si_erreur_lignearticle(
        self, admin_user, tenant, premier_pv, premier_produit_et_prix,
        asset_tlf, wallet_client, carte_client_avec_user,
    ):
        """Mock LigneArticle.objects.create → raise → Token.value revient, 0 Transaction.
        / Mock LigneArticle.objects.create → raise → Token.value reverts, 0 Transaction."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = premier_produit_et_prix
            prix_centimes = int(round(prix.prix * 100))

            _crediter_wallet(wallet_client, asset_tlf, 5000)

            solde_avant = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
            nb_transactions_avant = Transaction.objects.filter(
                tenant=tenant, action=Transaction.SALE,
                card=carte_client_avec_user,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client_avec_user.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            # Mocker LigneArticle.objects.create pour qu'il leve une exception
            # En mode DEBUG, DRF propage l'exception (raise_uncaught_exception)
            # / Mock LigneArticle.objects.create to raise an exception
            # In DEBUG mode, DRF propagates the exception (raise_uncaught_exception)
            with patch.object(
                LigneArticle.objects, 'create',
                side_effect=RuntimeError("Erreur simulee dans LigneArticle.create"),
            ):
                with pytest.raises(RuntimeError):
                    client.post('/laboutik/paiement/payer/', data=post_data)

            # Verifier : Token revient a sa valeur d'avant
            # / Verify: Token reverts to its previous value
            solde_apres = WalletService.obtenir_solde(wallet=wallet_client, asset=asset_tlf)
            assert solde_apres == solde_avant

            # Verifier : aucune Transaction SALE creee pour cette carte
            # / Verify: no SALE Transaction created for this card
            nb_transactions_apres = Transaction.objects.filter(
                tenant=tenant, action=Transaction.SALE,
                card=carte_client_avec_user,
            ).count()
            assert nb_transactions_apres == nb_transactions_avant
