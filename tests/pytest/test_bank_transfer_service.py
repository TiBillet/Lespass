"""
tests/pytest/test_bank_transfer_service.py — Tests unitaires BankTransferService (Phase 2).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_bank_transfer_service.py -v --api-key dummy
"""
import pytest

from fedow_core.exceptions import MontantSuperieurDette


def test_montant_superieur_dette_message():
    """
    Verifie que l'exception MontantSuperieurDette porte un message explicite
    incluant le montant demande ET la dette actuelle.
    / Verifies MontantSuperieurDette carries an explicit message.
    """
    exc = MontantSuperieurDette(
        montant_demande_en_centimes=1500,
        dette_actuelle_en_centimes=750,
    )
    message = str(exc)
    assert "1500" in message
    assert "750" in message


from django_tenants.utils import schema_context

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.services import WalletService


@pytest.fixture(scope="module")
def tenant_lespass_bt():
    return Client.objects.get(schema_name='lespass')


def test_get_or_create_wallet_tenant_creates_once(tenant_lespass_bt):
    """
    Premier appel cree le wallet, deuxieme appel le reutilise.
    Identifie par origin=tenant ET name=f"Lieu {schema_name}".
    """
    with schema_context('lespass'):
        wallet_a = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
        wallet_b = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
        assert wallet_a.pk == wallet_b.pk
        assert wallet_a.name == f"Lieu {tenant_lespass_bt.schema_name}"
        assert wallet_a.origin_id == tenant_lespass_bt.pk


from django.utils import timezone
from fedow_core.models import Asset, Token, Transaction
from fedow_core.services import AssetService, TransactionService


BT_TEST_PREFIX = '[bt_test]'


@pytest.fixture(scope="module")
def wallet_pot_central(tenant_lespass_bt):
    return Wallet.objects.create(name=f'{BT_TEST_PREFIX} Pot central')


@pytest.fixture(scope="module")
def asset_fed_test(tenant_lespass_bt, wallet_pot_central):
    """L'asset FED utilise pour les tests BankTransferService."""
    existing = Asset.objects.filter(category=Asset.FED).first()
    if existing is not None:
        return existing
    return AssetService.creer_asset(
        tenant=tenant_lespass_bt,
        name=f'{BT_TEST_PREFIX} FED',
        category=Asset.FED,
        currency_code='EUR',
        wallet_origin=wallet_pot_central,
    )


def test_bank_transfer_action_no_token_mutation(
    tenant_lespass_bt, wallet_pot_central, asset_fed_test,
):
    """
    Une Transaction action=BANK_TRANSFER ne doit ni debiter le sender
    ni crediter le receiver (mouvement bancaire externe).
    """
    receiver_wallet = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)

    # Solde initial sender et receiver
    solde_sender_avant = WalletService.obtenir_solde(wallet_pot_central, asset_fed_test)
    solde_receiver_avant = WalletService.obtenir_solde(receiver_wallet, asset_fed_test)

    TransactionService.creer(
        sender=wallet_pot_central,
        receiver=receiver_wallet,
        asset=asset_fed_test,
        montant_en_centimes=500,
        action=Transaction.BANK_TRANSFER,
        tenant=tenant_lespass_bt,
        ip="127.0.0.1",
        comment="Test no token mutation",
    )

    # Verifier qu'aucun solde n'a bouge
    solde_sender_apres = WalletService.obtenir_solde(wallet_pot_central, asset_fed_test)
    solde_receiver_apres = WalletService.obtenir_solde(receiver_wallet, asset_fed_test)
    assert solde_sender_apres == solde_sender_avant
    assert solde_receiver_apres == solde_receiver_avant

    # Verifier qu'une Transaction a bien ete creee
    tx = Transaction.objects.filter(
        action=Transaction.BANK_TRANSFER,
        sender=wallet_pot_central,
        receiver=receiver_wallet,
    ).order_by('-id').first()
    assert tx is not None
    assert tx.amount == 500


from BaseBillet.models import Product
from BaseBillet.services_refund import get_or_create_product_virement_recu


def test_get_or_create_product_virement_recu_creates_once():
    """Helper Product systeme 'Virement pot central' — idempotent."""
    with schema_context('lespass'):
        product_a = get_or_create_product_virement_recu()
        product_b = get_or_create_product_virement_recu()
        assert product_a.pk == product_b.pk
        assert product_a.methode_caisse == Product.VIREMENT_RECU
        assert product_a.publish is False


from datetime import date

from BaseBillet.models import LigneArticle, PaymentMethod, SaleOrigin
from fedow_core.services import BankTransferService


def test_calculer_dette_zero_si_aucune_transaction(
    tenant_lespass_bt, asset_fed_test,
):
    """Aucune transaction REFUND ou BANK_TRANSFER -> dette = 0."""
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 0


def test_calculer_dette_apres_un_refund(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """1 REFUND de 800c -> dette = 800c."""
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=800, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 800


def test_calculer_dette_apres_refund_et_virement(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """REFUND 1000c + BANK_TRANSFER 300c -> dette = 700c."""
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()

        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=1000, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )
        Transaction.objects.create(
            sender=wallet_pot_central, receiver=receiver,
            asset=asset_fed_test, amount=300, action=Transaction.BANK_TRANSFER,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        dette = BankTransferService.calculer_dette(
            tenant=tenant_lespass_bt, asset=asset_fed_test,
        )
        assert dette == 700


def test_enregistrer_virement_cree_transaction_et_lignearticle(
    tenant_lespass_bt, asset_fed_test, wallet_pot_central,
):
    """
    enregistrer_virement cree 1 Transaction BANK_TRANSFER + 1 LigneArticle TRANSFER positive,
    sans muter les Tokens.
    """
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        # Setup : creer une dette de 1000c via REFUND
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()
        LigneArticle.objects.filter(
            asset=asset_fed_test.uuid,
            payment_method=PaymentMethod.TRANSFER,
        ).delete()
        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=1000, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        # Action : enregistrer un virement de 400c
        tx = BankTransferService.enregistrer_virement(
            tenant=tenant_lespass_bt,
            asset=asset_fed_test,
            montant_en_centimes=400,
            date_virement=date.today(),
            reference_bancaire="VIR-TEST-001",
            comment="Test enregistrement",
            ip="127.0.0.1",
            admin_email="test@test.com",
        )

        assert tx.action == Transaction.BANK_TRANSFER
        assert tx.amount == 400
        assert tx.tenant_id == tenant_lespass_bt.pk

        # LigneArticle d'encaissement
        ligne = LigneArticle.objects.filter(
            asset=asset_fed_test.uuid,
            payment_method=PaymentMethod.TRANSFER,
            sale_origin=SaleOrigin.ADMIN,
        ).order_by('-datetime').first()
        assert ligne is not None
        assert ligne.amount == 400
        assert ligne.wallet_id == receiver.pk
        assert ligne.metadata.get("reference_bancaire") == "VIR-TEST-001"
        assert ligne.metadata.get("transaction_uuid") == str(tx.uuid)


def test_enregistrer_virement_rejette_si_montant_superieur_dette(
    tenant_lespass_bt, asset_fed_test,
):
    """Sur-versement -> MontantSuperieurDette."""
    receiver = WalletService.get_or_create_wallet_tenant(tenant_lespass_bt)
    with schema_context('lespass'):
        Transaction.objects.filter(
            asset=asset_fed_test,
            action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
            tenant=tenant_lespass_bt,
        ).delete()
        Transaction.objects.create(
            sender=receiver, receiver=receiver,
            asset=asset_fed_test, amount=200, action=Transaction.REFUND,
            tenant=tenant_lespass_bt, datetime=timezone.now(), ip="127.0.0.1",
        )

        with pytest.raises(MontantSuperieurDette):
            BankTransferService.enregistrer_virement(
                tenant=tenant_lespass_bt,
                asset=asset_fed_test,
                montant_en_centimes=500,  # > 200c de dette
                date_virement=date.today(),
                reference_bancaire="VIR-OVERFLOW-001",
                ip="127.0.0.1",
            )


@pytest.fixture(scope="module", autouse=True)
def cleanup_bt_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            wallets_test = Wallet.objects.filter(name__startswith=BT_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=BT_TEST_PREFIX)
            LigneArticle.objects.filter(asset__in=[a.uuid for a in assets_test]).delete()
            Transaction.objects.filter(asset__in=assets_test).delete()
            Token.objects.filter(wallet__in=wallets_test).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
