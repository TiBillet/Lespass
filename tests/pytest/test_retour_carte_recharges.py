"""
tests/pytest/test_retour_carte_recharges.py — Tests Phase 3 etape 2 :
retour carte (vrais soldes), recharges (RE/RC/TM), adhesions (AD).

Couvre : retour_carte avec fedow_core, recharges euros/cadeau/temps,
         adhesions via _creer_ou_renouveler_adhesion, sens des transactions.

Lancement / Run:
    docker exec lespass_django poetry run pytest tests/pytest/test_retour_carte_recharges.py -v --api-key dummy
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

from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from AuthBillet.models import TibilletUser, Wallet
from BaseBillet.models import (
    LigneArticle, Membership, PaymentMethod, Price,
    Product, SaleOrigin,
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
        email = 'admin-test-retour@tibillet.localhost'
        user, _ = TibilletUser.objects.get_or_create(
            email=email,
            defaults={
                'username': email,
                'is_staff': True,
                'is_active': True,
            },
        )
        user.client_admin.add(tenant)
        if not user.wallet:
            user.wallet = Wallet.objects.create(name='[test_retour] Admin')
            user.save(update_fields=['wallet'])
        return user


@pytest.fixture(scope="module")
def premier_pv(test_data):
    """Le premier point de vente (Bar).
    / The first point of sale (Bar)."""
    with schema_context(TENANT_SCHEMA):
        return PointDeVente.objects.filter(hidden=False).order_by('poid_liste').first()


@pytest.fixture(scope="module")
def wallet_lieu():
    """Wallet du lieu pour les assets.
    / Venue wallet for assets."""
    return Wallet.objects.create(name='[test_retour] Lieu')


@pytest.fixture(scope="module")
def wallet_lieu_tnf():
    """Wallet du lieu pour l'asset TNF.
    / Venue wallet for the TNF asset."""
    return Wallet.objects.create(name='[test_retour] Lieu TNF')


@pytest.fixture(scope="module")
def wallet_lieu_tim():
    """Wallet du lieu pour l'asset TIM.
    / Venue wallet for the TIM asset."""
    return Wallet.objects.create(name='[test_retour] Lieu TIM')


@pytest.fixture(scope="module")
def asset_tlf(tenant, wallet_lieu):
    """Asset TLF (monnaie locale euro) du tenant.
    / TLF asset (local fiat currency) for the tenant."""
    # Desactiver les autres TLF actifs du tenant
    # / Deactivate other active TLF assets for this tenant
    Asset.objects.filter(
        tenant_origin=tenant,
        category=Asset.TLF,
        active=True,
    ).update(active=False)

    return AssetService.creer_asset(
        tenant=tenant,
        name='TestCoin Retour',
        category=Asset.TLF,
        currency_code='EUR',
        wallet_origin=wallet_lieu,
    )


@pytest.fixture(scope="module")
def asset_tnf(tenant, wallet_lieu_tnf):
    """Asset TNF (monnaie cadeau) du tenant.
    / TNF asset (gift currency) for the tenant."""
    Asset.objects.filter(
        tenant_origin=tenant,
        category=Asset.TNF,
        active=True,
    ).update(active=False)

    return AssetService.creer_asset(
        tenant=tenant,
        name='TestCadeau Retour',
        category=Asset.TNF,
        currency_code='EUR',
        wallet_origin=wallet_lieu_tnf,
    )


@pytest.fixture(scope="module")
def asset_tim(tenant, wallet_lieu_tim):
    """Asset TIM (monnaie temps) du tenant.
    / TIM asset (time currency) for the tenant."""
    Asset.objects.filter(
        tenant_origin=tenant,
        category=Asset.TIM,
        active=True,
    ).update(active=False)

    return AssetService.creer_asset(
        tenant=tenant,
        name='TestTemps Retour',
        category=Asset.TIM,
        currency_code='TMP',
        wallet_origin=wallet_lieu_tim,
    )


@pytest.fixture(scope="module")
def wallet_client():
    """Wallet pour le client NFC.
    / Wallet for the NFC client."""
    return Wallet.objects.create(name='[test_retour] Client')


@pytest.fixture(scope="module")
def user_client(wallet_client):
    """Utilisateur client avec wallet.
    / Client user with wallet."""
    email = 'client-retour-test@tibillet.localhost'
    user, _ = TibilletUser.objects.get_or_create(
        email=email,
        defaults={'username': email, 'is_active': True},
    )
    user.wallet = wallet_client
    user.save(update_fields=['wallet'])
    return user


@pytest.fixture(scope="module")
def carte_client(user_client):
    """CarteCashless liee a user_client.
    / CarteCashless linked to user_client."""
    carte, _ = CarteCashless.objects.get_or_create(
        tag_id='NFCRET01',
        defaults={
            'number': 'NFCNMR01',
            'uuid': None,
            'user': user_client,
        },
    )
    if carte.user != user_client:
        carte.user = user_client
        carte.save(update_fields=['user'])
    return carte


@pytest.fixture(scope="module")
def produit_recharge_euros(premier_pv, test_data):
    """Product avec methode_caisse=RE + Price.
    / Product with methode_caisse=RE + Price."""
    with schema_context(TENANT_SCHEMA):
        produit, _ = Product.objects.get_or_create(
            name='Recharge EUR Test',
            defaults={
                'methode_caisse': Product.RECHARGE_EUROS,
                'publish': True,
            },
        )
        if not premier_pv.products.filter(pk=produit.pk).exists():
            premier_pv.products.add(produit)

        prix, _ = Price.objects.get_or_create(
            product=produit,
            prix=Decimal('10.00'),
            defaults={
                'publish': True,
                'subscription_type': Price.NA,
                'short_description': 'Recharge 10 EUR',
            },
        )
        return produit, prix


@pytest.fixture(scope="module")
def produit_recharge_cadeau(premier_pv, test_data):
    """Product avec methode_caisse=RC + Price.
    / Product with methode_caisse=RC + Price."""
    with schema_context(TENANT_SCHEMA):
        produit, _ = Product.objects.get_or_create(
            name='Recharge Cadeau Test',
            defaults={
                'methode_caisse': Product.RECHARGE_CADEAU,
                'publish': True,
            },
        )
        if not premier_pv.products.filter(pk=produit.pk).exists():
            premier_pv.products.add(produit)

        prix, _ = Price.objects.get_or_create(
            product=produit,
            prix=Decimal('5.00'),
            defaults={
                'publish': True,
                'subscription_type': Price.NA,
                'short_description': 'Cadeau 5 EUR',
            },
        )
        return produit, prix


@pytest.fixture(scope="module")
def produit_recharge_temps(premier_pv, test_data):
    """Product avec methode_caisse=TM + Price.
    / Product with methode_caisse=TM + Price."""
    with schema_context(TENANT_SCHEMA):
        produit, _ = Product.objects.get_or_create(
            name='Recharge Temps Test',
            defaults={
                'methode_caisse': Product.RECHARGE_TEMPS,
                'publish': True,
            },
        )
        if not premier_pv.products.filter(pk=produit.pk).exists():
            premier_pv.products.add(produit)

        prix, _ = Price.objects.get_or_create(
            product=produit,
            prix=Decimal('2.00'),
            defaults={
                'publish': True,
                'subscription_type': Price.NA,
                'short_description': 'Temps 2h',
            },
        )
        return produit, prix


@pytest.fixture(scope="module")
def produit_adhesion(premier_pv, test_data):
    """Product avec methode_caisse=AD + Price avec subscription_type=YEAR.
    / Product with methode_caisse=AD + Price with subscription_type=YEAR."""
    with schema_context(TENANT_SCHEMA):
        produit, _ = Product.objects.get_or_create(
            name='Adhesion POS Test',
            defaults={
                'methode_caisse': Product.ADHESION_POS,
                'categorie_article': Product.ADHESION,
                'publish': True,
            },
        )
        if not premier_pv.products.filter(pk=produit.pk).exists():
            premier_pv.products.add(produit)

        prix, _ = Price.objects.get_or_create(
            product=produit,
            prix=Decimal('15.00'),
            defaults={
                'publish': True,
                'subscription_type': Price.YEAR,
                'short_description': 'Adhesion annuelle test',
            },
        )
        return produit, prix


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crediter_wallet(wallet, asset, montant_centimes):
    """Credite un wallet avec un montant en centimes (dans un bloc atomic).
    / Credits a wallet with an amount in cents (inside an atomic block)."""
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
# Tests — retour_carte (vrais soldes)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRetourCarteVraisSoldes:
    """Test 1 : retour_carte affiche les vrais soldes depuis fedow_core."""

    def test_retour_carte_affiche_vrais_soldes(
        self, admin_user, tenant, asset_tlf, asset_tnf,
        wallet_client, carte_client,
    ):
        """POST retour_carte avec wallet TLF=5000 + TNF=2000
        → response contient '50' (TLF) et '20' (TNF)."""
        with schema_context(TENANT_SCHEMA):
            _crediter_wallet(wallet_client, asset_tlf, 5000)
            _crediter_wallet(wallet_client, asset_tnf, 2000)

            client = _make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/paiement/retour_carte/',
                data={'tag_id': carte_client.tag_id},
            )
            assert response.status_code == 200
            contenu = response.content.decode()

            # Les soldes doivent apparaitre dans le HTML
            # / Balances must appear in the HTML
            assert '50' in contenu, f"Attendu '50' (TLF), contenu : {contenu[:300]}"
            assert '20' in contenu, f"Attendu '20' (TNF), contenu : {contenu[:300]}"


@pytest.mark.usefixtures("test_data")
class TestRetourCarteAdhesions:
    """Test 2 : retour_carte affiche les adhesions actives."""

    def test_retour_carte_affiche_adhesions(
        self, admin_user, tenant, wallet_client, carte_client,
        user_client, produit_adhesion,
    ):
        """User avec Membership active → response contient le nom du produit."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_adhesion

            # Creer une Membership active
            # / Create an active Membership
            membership, created = Membership.objects.get_or_create(
                user=user_client,
                price=prix,
                defaults={
                    'status': Membership.LABOUTIK,
                    'last_contribution': timezone.now(),
                    'first_contribution': timezone.now(),
                    'contribution_value': prix.prix,
                },
            )
            if not created:
                membership.status = Membership.LABOUTIK
                membership.last_contribution = timezone.now()
                membership.save(update_fields=['status', 'last_contribution'])
            membership.set_deadline()

            client = _make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/paiement/retour_carte/',
                data={'tag_id': carte_client.tag_id},
            )
            assert response.status_code == 200
            contenu = response.content.decode()
            assert produit.name in contenu, (
                f"Attendu '{produit.name}' dans la reponse, contenu : {contenu[:300]}"
            )


@pytest.mark.usefixtures("test_data")
class TestRetourCarteSansWallet:
    """Test 3 : carte sans wallet → message d'erreur, pas de 500."""

    def test_retour_carte_sans_wallet(self, admin_user, tenant):
        """Carte sans user ni wallet_ephemere → erreur propre."""
        with schema_context(TENANT_SCHEMA):
            # Creer une carte sans user ni wallet_ephemere
            # / Create a card without user or wallet_ephemere
            carte_orpheline, _ = CarteCashless.objects.get_or_create(
                tag_id='NFCORP01',
                defaults={'number': 'NFCNMO01', 'uuid': None},
            )
            # S'assurer qu'elle n'a ni user ni wallet_ephemere
            # / Ensure no user and no wallet_ephemere
            carte_orpheline.user = None
            carte_orpheline.wallet_ephemere = None
            carte_orpheline.save(update_fields=['user', 'wallet_ephemere'])

            client = _make_client(admin_user, tenant)
            response = client.post(
                '/laboutik/paiement/retour_carte/',
                data={'tag_id': carte_orpheline.tag_id},
            )
            assert response.status_code == 200

            # Un wallet ephemere a ete cree automatiquement
            # / An ephemeral wallet was auto-created
            carte_orpheline.refresh_from_db()
            assert carte_orpheline.wallet_ephemere is not None, (
                "Un wallet ephemere aurait du etre cree automatiquement"
            )


# ---------------------------------------------------------------------------
# Tests — recharges (RE/RC/TM)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRechargeEuros:
    """Test 4 : recharge euros (RE) payee en especes → lieu debite, client credite en TLF."""

    def test_recharge_euros(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_lieu, wallet_client, carte_client,
        produit_recharge_euros,
    ):
        """POST payer avec produit RE + moyen espece + tag_id client → Token TLF client credite."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_euros
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet lieu pour qu'il ait de quoi distribuer
            # / Credit venue wallet so it can distribute
            _crediter_wallet(wallet_lieu, asset_tlf, 50000)

            solde_client_avant = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tlf,
            )
            nb_refill_avant = Transaction.objects.filter(
                tenant=tenant, action=Transaction.REFILL,
                receiver=wallet_client,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Token TLF client credite du montant
            # / Client TLF Token credited by amount
            solde_client_apres = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tlf,
            )
            assert solde_client_apres == solde_client_avant + prix_centimes

            # Transaction REFILL creee
            # / REFILL Transaction created
            nb_refill_apres = Transaction.objects.filter(
                tenant=tenant, action=Transaction.REFILL,
                receiver=wallet_client,
            ).count()
            assert nb_refill_apres == nb_refill_avant + 1

            # LigneArticle creee
            # / LigneArticle created
            derniere_ligne = LigneArticle.objects.filter(
                sale_origin=SaleOrigin.LABOUTIK,
                carte=carte_client,
            ).order_by('-datetime').first()
            assert derniere_ligne is not None


@pytest.mark.usefixtures("test_data")
class TestRechargeCadeau:
    """Test 5 : recharge cadeau (RC) → client credite en TNF."""

    def test_recharge_cadeau(
        self, admin_user, tenant, premier_pv, asset_tnf,
        wallet_lieu_tnf, wallet_client, carte_client,
        produit_recharge_cadeau,
    ):
        """POST payer avec produit RC → Token TNF client credite."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_cadeau
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet lieu TNF
            # / Credit venue TNF wallet
            _crediter_wallet(wallet_lieu_tnf, asset_tnf, 50000)

            solde_tnf_avant = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tnf,
            )

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok', obtenu : {contenu[:300]}"
            )

            # Token TNF client credite
            # / Client TNF Token credited
            solde_tnf_apres = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tnf,
            )
            assert solde_tnf_apres == solde_tnf_avant + prix_centimes

            # Transaction REFILL creee
            # / REFILL Transaction created
            derniere_tx = Transaction.objects.filter(
                tenant=tenant, action=Transaction.REFILL,
                asset=asset_tnf,
            ).order_by('-id').first()
            assert derniere_tx is not None


@pytest.mark.usefixtures("test_data")
class TestRechargeTemps:
    """Test 6 : recharge temps (TM) → client credite en TIM."""

    def test_recharge_temps(
        self, admin_user, tenant, premier_pv, asset_tim,
        wallet_lieu_tim, wallet_client, carte_client,
        produit_recharge_temps,
    ):
        """POST payer avec produit TM → Token TIM client credite."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_temps
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet lieu TIM
            # / Credit venue TIM wallet
            _crediter_wallet(wallet_lieu_tim, asset_tim, 50000)

            solde_tim_avant = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tim,
            )

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok', obtenu : {contenu[:300]}"
            )

            # Token TIM client credite
            # / Client TIM Token credited
            solde_tim_apres = WalletService.obtenir_solde(
                wallet=wallet_client, asset=asset_tim,
            )
            assert solde_tim_apres == solde_tim_avant + prix_centimes


# ---------------------------------------------------------------------------
# Tests — adhesions (AD)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestAdhesionCreeMembership:
    """Test 7 : adhesion (AD) payee en NFC → Membership creee avec status=LABOUTIK."""

    def test_adhesion_cree_membership(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_client, carte_client, user_client,
        produit_adhesion,
    ):
        """POST payer avec produit AD + moyen nfc → Membership creee."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_adhesion
            prix_centimes = int(round(prix.prix * 100))

            # Supprimer les anciennes adhesions pour ce test
            # / Delete old memberships for this test
            Membership.objects.filter(user=user_client, price=prix).delete()

            # Crediter le wallet client avec assez pour payer
            # / Credit client wallet with enough to pay
            _crediter_wallet(wallet_client, asset_tlf, prix_centimes + 1000)

            nb_memberships_avant = Membership.objects.filter(
                user=user_client, price=prix,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok', obtenu : {contenu[:300]}"
            )

            # Membership creee
            # / Membership created
            nb_memberships_apres = Membership.objects.filter(
                user=user_client, price=prix,
            ).count()
            assert nb_memberships_apres == nb_memberships_avant + 1

            # Verifier le status
            # / Verify the status
            derniere_membership = Membership.objects.filter(
                user=user_client, price=prix,
            ).order_by('-date_added').first()
            assert derniere_membership.status == Membership.LABOUTIK
            assert derniere_membership.deadline is not None


@pytest.mark.usefixtures("test_data")
class TestAdhesionRenouvelle:
    """Test 8 : adhesion (AD) NFC avec membership expiree → renouvellement."""

    def test_adhesion_renouvelle(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_client, carte_client, user_client,
        produit_adhesion,
    ):
        """Membership expiree → last_contribution mise a jour, deadline recalculee."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_adhesion
            prix_centimes = int(round(prix.prix * 100))

            # Creer une membership expiree
            # / Create an expired membership
            Membership.objects.filter(user=user_client, price=prix).delete()
            membership_expiree = Membership.objects.create(
                user=user_client,
                price=prix,
                status=Membership.LABOUTIK,
                last_contribution=timezone.now() - timedelta(days=400),
                first_contribution=timezone.now() - timedelta(days=400),
                contribution_value=prix.prix,
                deadline=timezone.now() - timedelta(days=35),
            )
            assert not membership_expiree.is_valid()

            # Crediter le wallet client
            # / Credit client wallet
            _crediter_wallet(wallet_client, asset_tlf, prix_centimes + 1000)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()
            assert "Transaction ok" in contenu, (
                f"Attendu 'Transaction ok', obtenu : {contenu[:300]}"
            )

            # Membership renouvelee (meme objet, pas de nouvelle ligne)
            # / Membership renewed (same object, no new row)
            membership_expiree.refresh_from_db()
            assert membership_expiree.is_valid()
            assert membership_expiree.status == Membership.LABOUTIK
            # last_contribution a ete mise a jour (recente)
            # / last_contribution was updated (recent)
            assert (timezone.now() - membership_expiree.last_contribution).total_seconds() < 60


# ---------------------------------------------------------------------------
# Tests — sens de la transaction recharge
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRechargeSensCorrect:
    """Test 9 : recharge RE → sender=lieu, receiver=client."""

    def test_recharge_sens_correct(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_lieu, wallet_client, carte_client,
        produit_recharge_euros,
    ):
        """Transaction.sender == wallet_lieu, Transaction.receiver == wallet_client."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_euros
            prix_centimes = int(round(prix.prix * 100))

            # Crediter le wallet lieu
            # / Credit venue wallet
            _crediter_wallet(wallet_lieu, asset_tlf, 50000)

            nb_tx_avant = Transaction.objects.filter(
                tenant=tenant, action=Transaction.REFILL,
            ).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Trouver la derniere transaction REFILL
            # / Find the latest REFILL transaction
            derniere_tx = Transaction.objects.filter(
                tenant=tenant, action=Transaction.REFILL,
            ).order_by('-id').first()
            assert derniere_tx is not None

            # Verifier le sens : lieu → client
            # / Verify direction: venue → client
            assert derniere_tx.sender == wallet_lieu, (
                f"Attendu sender=wallet_lieu, obtenu sender={derniere_tx.sender}"
            )
            assert derniere_tx.receiver == wallet_client, (
                f"Attendu receiver=wallet_client, obtenu receiver={derniere_tx.receiver}"
            )


# ---------------------------------------------------------------------------
# Tests — securite (Phase 3.2)
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("test_data")
class TestRechargeNFCRejete:
    """Test 10 : recharge (RE) payee en NFC → rejete explicitement."""

    def test_recharge_nfc_rejete(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_lieu, wallet_client, carte_client,
        produit_recharge_euros,
    ):
        """POST payer moyen=nfc + produit RE → rejet 400, pas de Transaction."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_euros
            prix_centimes = int(round(prix.prix * 100))

            _crediter_wallet(wallet_lieu, asset_tlf, 50000)

            nb_tx_avant = Transaction.objects.filter(tenant=tenant).count()

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'nfc',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_client.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 400
            contenu = response.content.decode()
            assert 'cashless' in contenu.lower() or 'recharge' in contenu.lower(), (
                f"Attendu message d'erreur recharge/cashless, obtenu : {contenu[:300]}"
            )

            # Aucune transaction creee
            # / No transaction created
            nb_tx_apres = Transaction.objects.filter(tenant=tenant).count()
            assert nb_tx_apres == nb_tx_avant


@pytest.mark.usefixtures("test_data")
class TestPanierMixteForceEspecesCB:
    """Test 11 : panier VT+RE → NFC absent des moyens proposes."""

    def test_panier_mixte_pas_de_nfc(
        self, admin_user, tenant, premier_pv,
        produit_recharge_euros,
    ):
        """POST moyens_paiement avec article RE → 'nfc' pas dans la reponse."""
        with schema_context(TENANT_SCHEMA):
            produit, prix = produit_recharge_euros

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/moyens_paiement/', data=post_data)
            assert response.status_code == 200
            contenu = response.content.decode()

            # Le bouton CASHLESS ne doit pas apparaitre
            # / The CASHLESS button must not appear
            assert 'CASHLESS' not in contenu, (
                f"Le bouton CASHLESS ne devrait pas etre propose pour une recharge"
            )
            # Mais ESPECE ou CB doivent etre proposes
            # / But CASH or CC must be offered
            assert 'recharge' in contenu.lower() or 'ESP' in contenu or 'CB' in contenu, (
                f"Attendu des moyens espece/CB, contenu : {contenu[:500]}"
            )


@pytest.mark.usefixtures("test_data")
class TestWalletEphemereAutoCree:
    """Test 12 : carte sans wallet → wallet ephemere cree automatiquement."""

    def test_wallet_ephemere_auto_cree(
        self, admin_user, tenant, premier_pv, asset_tlf,
        wallet_lieu, produit_recharge_euros,
    ):
        """Carte sans user ni wallet → wallet ephemere cree, recharge OK."""
        with schema_context(TENANT_SCHEMA):
            # Creer une carte orpheline (pas de user, pas de wallet_ephemere)
            # / Create an orphan card (no user, no wallet_ephemere)
            carte_orpheline, _ = CarteCashless.objects.get_or_create(
                tag_id='NFCEPH01',
                defaults={'number': 'NFCNME01', 'uuid': None},
            )
            carte_orpheline.user = None
            carte_orpheline.wallet_ephemere = None
            carte_orpheline.save(update_fields=['user', 'wallet_ephemere'])

            produit, prix = produit_recharge_euros
            prix_centimes = int(round(prix.prix * 100))

            _crediter_wallet(wallet_lieu, asset_tlf, 50000)

            client = _make_client(admin_user, tenant)
            post_data = {
                'uuid_pv': str(premier_pv.uuid),
                'moyen_paiement': 'espece',
                'total': str(prix_centimes),
                'given_sum': '',
                'tag_id': carte_orpheline.tag_id,
                f'repid-{produit.uuid}': '1',
            }

            response = client.post('/laboutik/paiement/payer/', data=post_data)
            assert response.status_code == 200

            # Wallet ephemere cree automatiquement
            # / Ephemeral wallet auto-created
            carte_orpheline.refresh_from_db()
            assert carte_orpheline.wallet_ephemere is not None, (
                "Wallet ephemere aurait du etre cree"
            )

            # Solde credite sur le wallet ephemere
            # / Balance credited on ephemeral wallet
            solde = WalletService.obtenir_solde(
                wallet=carte_orpheline.wallet_ephemere, asset=asset_tlf,
            )
            assert solde == prix_centimes


@pytest.mark.usefixtures("test_data")
class TestValidationPVCartePrimaire:
    """Test 13 : PV non autorise pour la carte primaire → PermissionDenied."""

    def test_validation_pv_carte_primaire(
        self, admin_user, tenant, premier_pv,
    ):
        """Acces a un PV non autorise via carte primaire → 403."""
        with schema_context(TENANT_SCHEMA):
            from laboutik.models import CartePrimaire

            # Creer une carte primaire SANS acces au premier PV
            # / Create a primary card WITHOUT access to the first PV
            carte_cm, _ = CarteCashless.objects.get_or_create(
                tag_id='NFCPV01',
                defaults={'number': 'NFCNPV01', 'uuid': None},
            )
            carte_prim, _ = CartePrimaire.objects.get_or_create(
                carte=carte_cm,
                defaults={'edit_mode': False},
            )
            # S'assurer qu'elle n'a PAS acces au premier PV
            # / Ensure it does NOT have access to the first PV
            carte_prim.points_de_vente.clear()

            client = _make_client(admin_user, tenant)
            response = client.get(
                f'/laboutik/caisse/point_de_vente/?uuid_pv={premier_pv.uuid}&tag_id_cm={carte_cm.tag_id}',
            )
            assert response.status_code == 403
