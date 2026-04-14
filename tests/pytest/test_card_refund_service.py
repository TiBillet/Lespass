"""
tests/pytest/test_card_refund_service.py — Tests unitaires WalletService.rembourser_en_especes (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_card_refund_service.py -v --api-key dummy
"""
import pytest
from django_tenants.utils import schema_context

from fedow_core.exceptions import NoEligibleTokens
from BaseBillet.models import Product
from BaseBillet.services_refund import (
    get_or_create_product_remboursement,
    get_or_create_pricesold_refund,
)


def test_no_eligible_tokens_exception_message():
    """
    Verifie que l'exception NoEligibleTokens porte un message explicite
    incluant le tag_id et la chaine de base (en francais).
    / Verifies NoEligibleTokens carries an explicit message including the
    tag_id and the base string (in French).
    """
    from django.utils.translation import override
    # Instancier ET evaluer le message en francais dans le meme contexte
    with override('fr'):
        exc = NoEligibleTokens(carte_tag_id="ABCD1234")
        message_fr = str(exc)
    assert "ABCD1234" in message_fr
    assert "Aucun solde remboursable" in message_fr


def test_get_or_create_product_remboursement_creates_once():
    """
    Premier appel cree le Product systeme, deuxieme appel le reutilise.
    First call creates the system Product, second call reuses it.
    """
    with schema_context('lespass'):
        product_a = get_or_create_product_remboursement()
        product_b = get_or_create_product_remboursement()
        assert product_a.pk == product_b.pk
        assert product_a.methode_caisse == Product.VIDER_CARTE


def test_get_or_create_pricesold_refund_creates_once():
    """
    Le PriceSold de remboursement est unique et reutilisable.
    Refund PriceSold is unique and reusable.
    """
    with schema_context('lespass'):
        product = get_or_create_product_remboursement()
        ps_a = get_or_create_pricesold_refund(product)
        ps_b = get_or_create_pricesold_refund(product)
        assert ps_a.pk == ps_b.pk
        assert ps_a.productsold.product.pk == product.pk


# ---------------------------------------------------------------------------
# Tests WalletService.rembourser_en_especes — Task 3
# ---------------------------------------------------------------------------

import uuid as uuid_module
from django.db import transaction as db_transaction
from django_tenants.utils import tenant_context

from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, WalletService
from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin

REFUND_TEST_PREFIX = '[refund_test]'


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def wallet_lieu_lespass(tenant_lespass):
    """Wallet du lieu lespass (recepteur des refunds)."""
    return Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} Lieu Lespass')


@pytest.fixture(scope="module")
def asset_tlf_lespass(tenant_lespass, wallet_lieu_lespass):
    # get_or_create pour eviter l'IntegrityError si un run precedent n'a pas nettoye
    # / get_or_create to avoid IntegrityError if a previous run did not clean up
    asset, _created = Asset.objects.get_or_create(
        name=f'{REFUND_TEST_PREFIX} TLF Lespass',
        category=Asset.TLF,
        defaults={
            'currency_code': 'EUR',
            'wallet_origin': wallet_lieu_lespass,
            'tenant_origin': tenant_lespass,
        },
    )
    return asset


@pytest.fixture(scope="module")
def asset_fed_unique(tenant_lespass, wallet_lieu_lespass):
    """L'asset FED unique du systeme (decision projet : 1 seul FED)."""
    existing = Asset.objects.filter(category=Asset.FED).first()
    if existing is not None:
        return existing
    return AssetService.creer_asset(
        tenant=tenant_lespass,
        name=f'{REFUND_TEST_PREFIX} FED',
        category=Asset.FED,
        currency_code='EUR',
        wallet_origin=wallet_lieu_lespass,
    )


@pytest.fixture
def carte_avec_solde_tlf(tenant_lespass, asset_tlf_lespass):
    """Carte anonyme avec wallet_ephemere et 1000 centimes TLF."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} Wallet user TLF')
        carte = CarteCashless.objects.create(
            tag_id='RFT00001',
            number='RFT00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user, asset=asset_tlf_lespass, montant_en_centimes=1000,
            )
        yield carte
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


@pytest.fixture
def carte_avec_solde_fed(tenant_lespass, asset_fed_unique):
    """Carte anonyme avec wallet_ephemere et 500 centimes FED."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_user = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} Wallet user FED')
        carte = CarteCashless.objects.create(
            tag_id='RFT00002',
            number='RFT00002',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_user,
        )
        with db_transaction.atomic():
            WalletService.crediter(
                wallet=wallet_user, asset=asset_fed_unique, montant_en_centimes=500,
            )
        yield carte
        LigneArticle.objects.filter(carte=carte).delete()
        Transaction.objects.filter(card=carte).delete()
        Token.objects.filter(wallet=wallet_user).delete()
        carte.delete()
        wallet_user.delete()


def test_rembourser_carte_avec_user_tlf_seul(
    tenant_lespass, wallet_lieu_lespass, asset_tlf_lespass, carte_avec_solde_tlf,
):
    """1000c TLF -> 1 Transaction REFUND + 1 LigneArticle CASH (-1000). Solde -> 0."""
    with tenant_context(tenant_lespass):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_avec_solde_tlf,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
            ip="127.0.0.1",
            vider_carte=False,
        )
        assert resultat["total_centimes"] == 1000
        assert resultat["total_tlf_centimes"] == 1000
        assert resultat["total_fed_centimes"] == 0
        assert len(resultat["transactions"]) == 1

        wallet_user = carte_avec_solde_tlf.wallet_ephemere
        solde = WalletService.obtenir_solde(wallet=wallet_user, asset=asset_tlf_lespass)
        assert solde == 0

        lignes_cash = LigneArticle.objects.filter(
            carte=carte_avec_solde_tlf,
            payment_method=PaymentMethod.CASH,
            sale_origin=SaleOrigin.ADMIN,
        )
        assert lignes_cash.count() == 1
        assert lignes_cash.first().amount == -1000

        lignes_fed = LigneArticle.objects.filter(
            carte=carte_avec_solde_tlf, payment_method=PaymentMethod.STRIPE_FED,
        )
        assert lignes_fed.count() == 0


def test_rembourser_carte_avec_user_fed_seul(
    tenant_lespass, wallet_lieu_lespass, asset_fed_unique, carte_avec_solde_fed,
):
    """500c FED -> 1 LigneArticle FED (+500) + 1 LigneArticle CASH (-500)."""
    with tenant_context(tenant_lespass):
        resultat = WalletService.rembourser_en_especes(
            carte=carte_avec_solde_fed,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
        )
        assert resultat["total_fed_centimes"] == 500
        assert resultat["total_tlf_centimes"] == 0

        ligne_fed = LigneArticle.objects.filter(
            carte=carte_avec_solde_fed, payment_method=PaymentMethod.STRIPE_FED,
        )
        assert ligne_fed.count() == 1
        assert ligne_fed.first().amount == 500

        ligne_cash = LigneArticle.objects.filter(
            carte=carte_avec_solde_fed, payment_method=PaymentMethod.CASH,
        )
        assert ligne_cash.count() == 1
        assert ligne_cash.first().amount == -500


def test_rembourser_exclut_tnf_tim_fid(tenant_lespass, wallet_lieu_lespass):
    """Tokens TNF/TIM/FID ignores : NoEligibleTokens levee."""
    import time
    # Utilise timestamp court pour eviter les collisions de nom entre les runs de tests
    # / Use short timestamp to avoid name collisions between test runs
    unique_suffix = str(int(time.time() * 1000) % 10000)

    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        wallet_eph = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} TNF {unique_suffix}')
        carte = CarteCashless.objects.create(
            tag_id=f'RFTN{unique_suffix}',
            number=f'RFTN{unique_suffix}',
            uuid=uuid_module.uuid4(),
            detail=detail,
            wallet_ephemere=wallet_eph,
        )
        wallet_origine_tnf = Wallet.objects.create(name=f'{REFUND_TEST_PREFIX} TNF o {unique_suffix}')
        asset_tnf = AssetService.creer_asset(
            tenant=tenant_lespass,
            name=f'{REFUND_TEST_PREFIX} TNF c {unique_suffix}',
            category=Asset.TNF,
            currency_code='EUR',
            wallet_origin=wallet_origine_tnf,
        )
        with db_transaction.atomic():
            WalletService.crediter(wallet=wallet_eph, asset=asset_tnf, montant_en_centimes=300)

        with tenant_context(tenant_lespass):
            from fedow_core.exceptions import NoEligibleTokens
            with pytest.raises(NoEligibleTokens):
                WalletService.rembourser_en_especes(
                    carte=carte,
                    tenant=tenant_lespass,
                    receiver_wallet=wallet_lieu_lespass,
                )

        Token.objects.filter(wallet=wallet_eph).delete()
        carte.delete()
        wallet_eph.delete()
        Asset.objects.filter(name__icontains=f'TNF c {unique_suffix}').delete()
        wallet_origine_tnf.delete()


def test_rembourser_avec_vider_carte_reset(
    tenant_lespass, wallet_lieu_lespass, asset_tlf_lespass, carte_avec_solde_tlf,
):
    """vider_carte=True -> carte.user=None, wallet_ephemere=None."""
    with tenant_context(tenant_lespass):
        WalletService.rembourser_en_especes(
            carte=carte_avec_solde_tlf,
            tenant=tenant_lespass,
            receiver_wallet=wallet_lieu_lespass,
            vider_carte=True,
        )
        carte_avec_solde_tlf.refresh_from_db()
        assert carte_avec_solde_tlf.user is None
        assert carte_avec_solde_tlf.wallet_ephemere is None


def test_rembourser_carte_vide_raise_no_eligible(tenant_lespass, wallet_lieu_lespass):
    """Carte sans wallet -> NoEligibleTokens."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{REFUND_TEST_PREFIX}_TEST',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte_vide = CarteCashless.objects.create(
            tag_id='RFT00004',
            number='RFT00004',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        with tenant_context(tenant_lespass):
            from fedow_core.exceptions import NoEligibleTokens
            with pytest.raises(NoEligibleTokens):
                WalletService.rembourser_en_especes(
                    carte=carte_vide,
                    tenant=tenant_lespass,
                    receiver_wallet=wallet_lieu_lespass,
                )
        carte_vide.delete()


@pytest.fixture(scope="module", autouse=True)
def cleanup_refund_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            from BaseBillet.models import LigneArticle, Price, Product
            wallets_test = Wallet.objects.filter(name__startswith=REFUND_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=REFUND_TEST_PREFIX)
            LigneArticle.objects.filter(carte__tag_id__startswith='RFT').delete()
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            CarteCashless.objects.filter(tag_id__startswith='RFT').delete()
            Detail.objects.filter(base_url=f'{REFUND_TEST_PREFIX}_TEST').delete()
            # Supprimer les Products crees par le signal post_save Asset
            # (signal auto-cree "Recharge <asset_name>" pour chaque Asset)
            # / Delete Products created by the Asset post_save signal
            # (signal auto-creates "Recharge <asset_name>" for each Asset)
            for asset in assets_test:
                Price.objects.filter(product__name=f'Recharge {asset.name}').delete()
                Product.objects.filter(name=f'Recharge {asset.name}').delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
