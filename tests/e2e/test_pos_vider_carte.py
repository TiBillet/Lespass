"""
tests/e2e/test_pos_vider_carte.py — Test E2E flow POS "Vider Carte" Phase 3.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/e2e/test_pos_vider_carte.py -v -s
"""
import pytest


@pytest.fixture
def setup_vider_carte_e2e(django_shell):
    """
    Setup en DB :
    - PV 'E2E VC PV' avec Product VIDER_CARTE au M2M.
    - CartePrimaire du caissier liee au PV.
    - Carte client avec wallet_ephemere + 1000c TLF.

    / DB setup:
    - POS 'E2E VC PV' with VIDER_CARTE Product in M2M.
    - Primary cashier card linked to the POS.
    - Client card with wallet_ephemere + 1000c TLF.
    """
    setup_code = '''
import uuid
from django.db import transaction as db_transaction
from AuthBillet.models import Wallet
from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Transaction, Token
from fedow_core.services import WalletService
from laboutik.models import CartePrimaire, PointDeVente
from BaseBillet.services_refund import get_or_create_product_remboursement

tenant = Client.objects.get(schema_name='lespass')

wallet_lieu, _ = Wallet.objects.get_or_create(name='E2E VC Lieu')

asset_tlf, _ = Asset.objects.get_or_create(
    name='E2E VC TLF',
    category=Asset.TLF,
    defaults={
        'currency_code': 'EUR',
        'wallet_origin': wallet_lieu,
        'tenant_origin': tenant,
    },
)

detail, _ = Detail.objects.get_or_create(
    base_url='E2E_VC',
    origine=tenant,
    defaults={'generation': 0},
)

carte_caissier, _ = CarteCashless.objects.get_or_create(
    tag_id='E2EVC001',
    defaults={
        'number': 'E2EVC001',
        'uuid': uuid.uuid4(),
        'detail': detail,
    },
)
pv, _ = PointDeVente.objects.get_or_create(
    name='E2E VC PV',
    defaults={'comportement': 'V', 'hidden': False},
)
cp, _ = CartePrimaire.objects.get_or_create(
    carte=carte_caissier,
    defaults={'edit_mode': False},
)
cp.points_de_vente.add(pv)
product_vc = get_or_create_product_remboursement()
pv.products.add(product_vc)

wallet_client = Wallet.objects.create(name='E2E VC Wallet client')
carte_client, created_cc = CarteCashless.objects.get_or_create(
    tag_id='E2EVC002',
    defaults={
        'number': 'E2EVC002',
        'uuid': uuid.uuid4(),
        'detail': detail,
        'wallet_ephemere': wallet_client,
    },
)
if not created_cc:
    carte_client.wallet_ephemere = wallet_client
    carte_client.user = None
    carte_client.save()

Transaction.objects.filter(card=carte_client).delete()

with db_transaction.atomic():
    WalletService.crediter(wallet=wallet_client, asset=asset_tlf, montant_en_centimes=1000)

print('SETUP_OK')
print(f'pv_uuid:{pv.uuid}')
'''
    out = django_shell(setup_code)
    assert 'SETUP_OK' in out, f'Setup failed: {out}'

    yield

    teardown_code = '''
from AuthBillet.models import Wallet
from QrcodeCashless.models import CarteCashless, Detail
from fedow_core.models import Asset, Transaction, Token
from laboutik.models import CartePrimaire, PointDeVente
from BaseBillet.models import LigneArticle, Price, Product

assets_e2e_vc = list(Asset.objects.filter(name__startswith='E2E VC'))

# Supprimer Transactions et LigneArticles lies aux cartes E2E VC.
# / Delete Transactions and LigneArticles linked to E2E VC cards.
for carte in CarteCashless.objects.filter(tag_id__startswith='E2EVC'):
    LigneArticle.objects.filter(carte=carte).delete()
    Transaction.objects.filter(card=carte).delete()
    # primary_card est PROTECTED : supprimer aussi les Transactions referentes.
    # / primary_card is PROTECTED: also delete Transactions that reference it.
    Transaction.objects.filter(primary_card=carte).delete()

# Supprimer les Transactions referençant les Assets E2E VC (evite ProtectedError sur Token).
# / Delete Transactions referencing E2E VC Assets (avoids ProtectedError on Token).
Transaction.objects.filter(asset__in=assets_e2e_vc).delete()

# Supprimer les Tokens lies aux Assets E2E VC (Token.asset est PROTECTED).
# / Delete Tokens linked to E2E VC Assets (Token.asset is PROTECTED).
Token.objects.filter(asset__in=assets_e2e_vc).delete()

# Supprimer cartes + wallets ephemeres.
# / Delete cards + ephemeral wallets.
for carte in CarteCashless.objects.filter(tag_id__startswith='E2EVC'):
    weph = carte.wallet_ephemere
    carte.delete()
    if weph:
        Token.objects.filter(wallet=weph).delete()
        weph.delete()

# Supprimer les Products crees par le signal post_save Asset (ex: "Recharge E2E VC TLF").
# / Delete Products created by the Asset post_save signal (e.g. "Recharge E2E VC TLF").
prods_e2e_vc = Product.objects.filter(name__icontains='E2E VC')
for p in prods_e2e_vc:
    Price.objects.filter(product=p).delete()
prods_e2e_vc.delete()

Asset.objects.filter(name__startswith='E2E VC').delete()
Wallet.objects.filter(name__startswith='E2E VC').delete()
PointDeVente.objects.filter(name='E2E VC PV').delete()
Detail.objects.filter(base_url='E2E_VC').delete()
print('TEARDOWN_OK')
'''
    django_shell(teardown_code)


def test_e2e_pos_vider_carte_flow_complet(
    page, login_as_admin, django_shell, setup_vider_carte_e2e,
):
    """
    Flow complet via POST direct (simulation NFC cote UI fragile).
    1. Login admin.
    2. POST sur /laboutik/paiement/vider_carte/ comme si le scan NFC avait eu lieu.
    3. Verifier que la reponse contient le recap de succes (total 1000c).
    4. Verifier en DB : 1 Transaction REFUND + 1 LigneArticle CASH (-1000).

    / Complete flow via direct POST (NFC UI simulation unreliable).
    1. Admin login.
    2. POST to /laboutik/paiement/vider_carte/ as if NFC scan had occurred.
    3. Verify response contains success summary (total 1000c).
    4. Verify in DB: 1 REFUND Transaction + 1 CASH LigneArticle (-1000).
    """
    # 1. Login admin via TEST MODE flow.
    login_as_admin(page)

    # 2. Recupere le pv_uuid via django_shell.
    # / Get pv_uuid via django_shell.
    get_uuid_code = '''
from laboutik.models import PointDeVente
pv = PointDeVente.objects.get(name='E2E VC PV')
print(f'pv_uuid:{pv.uuid}')
'''
    out = django_shell(get_uuid_code)
    pv_uuid = [
        line.split(':', 1)[1]
        for line in out.split('\n')
        if line.startswith('pv_uuid:')
    ][0]

    # 3. Recuperer le token CSRF depuis les cookies (necessaire pour la session admin).
    # / Retrieve CSRF token from cookies (required for admin session).
    # DRF applique le CSRF quand l'auth est par session (pas API key).
    # / DRF enforces CSRF when auth is via session (not API key).
    page.goto('/laboutik/caisse/')
    page.wait_for_load_state('domcontentloaded')
    cookies = page.context.cookies()
    csrf_token = next(
        (c['value'] for c in cookies if c['name'] == 'csrftoken'),
        None,
    )
    assert csrf_token, f'csrftoken cookie introuvable apres goto caisse. Cookies: {cookies}'

    # 4. POST direct sur vider_carte (bypass UI NFC).
    # / Direct POST on vider_carte (bypass NFC UI).
    response = page.request.post(
        '/laboutik/paiement/vider_carte/',
        form={
            'tag_id': 'E2EVC002',
            'tag_id_cm': 'E2EVC001',
            'uuid_pv': pv_uuid,
            'vider_carte': 'false',
        },
        headers={
            'X-CSRFToken': csrf_token,
            'Referer': 'https://lespass.tibillet.localhost/laboutik/caisse/',
        },
    )
    assert response.ok, f'POST vider_carte failed: {response.status}'
    body = response.text()
    # La reponse HTML doit contenir le total 1000c formate en euros (10,00 €).
    # / HTML response must contain the 1000c total formatted as euros (10,00 €).
    assert '10,00' in body, f'Total 10,00 € absent de la reponse: {body[:500]}'

    # 4. Verifier en DB.
    # / Verify in DB.
    check_code = '''
from fedow_core.models import Transaction
from BaseBillet.models import LigneArticle, PaymentMethod
from QrcodeCashless.models import CarteCashless

carte_client = CarteCashless.objects.get(tag_id='E2EVC002')
nb_refund = Transaction.objects.filter(card=carte_client, action=Transaction.REFUND).count()
nb_la_cash = LigneArticle.objects.filter(
    carte=carte_client, payment_method=PaymentMethod.CASH,
).count()
print(f'REFUND_COUNT:{nb_refund}')
print(f'CASH_COUNT:{nb_la_cash}')
'''
    out = django_shell(check_code)
    assert 'REFUND_COUNT:1' in out, f'Expected 1 REFUND, got: {out}'
    assert 'CASH_COUNT:1' in out, f'Expected 1 CASH LigneArticle, got: {out}'
