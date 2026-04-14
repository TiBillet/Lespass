"""
tests/e2e/test_admin_bank_transfer_flow.py — Test E2E flow saisie virement Phase 2.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_admin_bank_transfer_flow.py -v -s
"""
import pytest


@pytest.fixture
def setup_dette_e2e(django_shell):
    """
    Setup en DB : creer un asset FED + une Transaction REFUND simulee de 1000c
    pour avoir une dette de 1000c sur le tenant lespass.
    Cleanup : supprimer transactions/assets/wallets/lignes E2E.
    """
    setup_code = '''
from django.utils import timezone
from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Transaction
from fedow_core.services import WalletService

tenant = Client.objects.get(schema_name='lespass')

wallet_pc, _ = Wallet.objects.get_or_create(name='E2E_BT Pot central')

asset_fed = Asset.objects.filter(category=Asset.FED).first()
if asset_fed is None:
    asset_fed = Asset.objects.create(
        name='E2E_BT FED',
        category=Asset.FED,
        currency_code='EUR',
        wallet_origin=wallet_pc,
        tenant_origin=tenant,
    )

receiver = WalletService.get_or_create_wallet_tenant(tenant)

Transaction.objects.filter(
    action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
    asset=asset_fed,
    tenant=tenant,
).delete()

Transaction.objects.create(
    sender=receiver, receiver=receiver,
    asset=asset_fed, amount=1000, action=Transaction.REFUND,
    tenant=tenant, datetime=timezone.now(), ip='127.0.0.1',
)

print('SETUP_OK')
print(f'asset_uuid:{asset_fed.uuid}')
print(f'tenant_uuid:{tenant.uuid}')
'''
    out = django_shell(setup_code)
    assert "SETUP_OK" in out

    yield

    teardown_code = '''
from AuthBillet.models import Wallet
from fedow_core.models import Asset, Transaction
from BaseBillet.models import LigneArticle, PaymentMethod

Transaction.objects.filter(
    action__in=[Transaction.REFUND, Transaction.BANK_TRANSFER],
    asset__name__startswith='E2E_BT',
).delete()
LigneArticle.objects.filter(
    payment_method=PaymentMethod.TRANSFER,
    metadata__contains={'reference_bancaire': 'VIR-E2E-001'},
).delete()
Asset.objects.filter(name__startswith='E2E_BT').delete()
Wallet.objects.filter(name__startswith='E2E_BT').delete()
print('TEARDOWN_OK')
'''
    django_shell(teardown_code)


def test_e2e_superuser_enregistre_virement(page, login_as_admin, django_shell, setup_dette_e2e):
    """
    Flow complet :
    1. Login admin (doit etre superuser pour acceder a /admin/bank-transfers/).
    2. Naviguer vers le dashboard.
    3. Verifier que la dette de 1000c est affichee.
    4. Cliquer "Enregistrer un virement", remplir 4 EUR, soumettre.
    5. Verifier la redirection vers /admin/bank-transfers/ (dashboard).
    6. Verifier en DB : 1 Transaction BANK_TRANSFER + 1 LigneArticle TRANSFER.
    """
    login_as_admin(page)

    check_superuser = django_shell('''
from django.contrib.auth import get_user_model
u = get_user_model().objects.filter(email='admin@admin.com').first()
print(f'is_superuser:{u.is_superuser if u else False}')
''')
    if "is_superuser:True" not in check_superuser:
        pytest.skip("L'admin de test n'est pas superuser, ce test E2E demande un superuser")

    page.goto("/admin/bank-transfers/")
    page.wait_for_load_state("domcontentloaded")

    page.wait_for_selector('[data-testid="bank-transfers-dashboard"]', timeout=10_000)
    contenu = page.content()
    assert "1000" in contenu, "Dette de 1000c introuvable dans le dashboard"

    page.click('[data-testid^="btn-saisir-virement-"]')

    page.fill('[data-testid="input-montant"]', "4.00")
    page.fill('[data-testid="input-date"]', "2026-04-13")
    page.fill('[data-testid="input-reference"]', "VIR-E2E-001")
    page.fill('[data-testid="input-comment"]', "Test E2E")

    page.click('[data-testid="btn-submit-virement"]')

    page.wait_for_url(
        lambda url: "/admin/bank-transfers/" in url and "/historique" not in url,
        timeout=10_000,
    )

    verify_code = '''
from fedow_core.models import Transaction
from BaseBillet.models import LigneArticle, PaymentMethod
nb_bt = Transaction.objects.filter(action=Transaction.BANK_TRANSFER, amount=400).count()
nb_la = LigneArticle.objects.filter(
    payment_method=PaymentMethod.TRANSFER, amount=400,
    metadata__contains={'reference_bancaire': 'VIR-E2E-001'},
).count()
print(f'BT_COUNT:{nb_bt}')
print(f'LA_COUNT:{nb_la}')
'''
    out = django_shell(verify_code)
    assert "BT_COUNT:1" in out, f"Expected 1 BANK_TRANSFER, got: {out}"
    assert "LA_COUNT:1" in out, f"Expected 1 LigneArticle TRANSFER, got: {out}"
