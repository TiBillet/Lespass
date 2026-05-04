"""
tests/pytest/test_admin_bank_transfers.py — Tests permissions et flow admin Phase 2.

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_bank_transfers.py -v --api-key dummy
"""
import uuid as uuid_module

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django_tenants.utils import schema_context

from AuthBillet.models import Wallet
from Customers.models import Client
from fedow_core.models import Asset, Transaction


ADM_BT_TEST_PREFIX = '[adm_bt_test]'


@pytest.fixture(scope="module")
def tenant_lespass_admin_bt():
    return Client.objects.get(schema_name='lespass')


def _login_as_admin():
    """Cree un client de test login en tant qu'admin."""
    client = TestClient(HTTP_HOST='lespass.tibillet.localhost')
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable")
    # Signal pre_save peut mettre is_active=False (cf. PIEGES.md 9.88).
    # / Pre_save signal may set is_active=False (see PIEGES.md 9.88).
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active'])
    client.force_login(user)
    return client, user


def test_dashboard_403_pour_non_superuser():
    """GET /admin/bank-transfers/ -> 403 si pas superuser."""
    client, user = _login_as_admin()
    if user.is_superuser:
        pytest.skip("L'admin de test est superuser, on teste le superuser dans test_dashboard_200")

    response = client.get('/admin/bank-transfers/')
    # Soit 403 direct, soit redirige vers login si pas authentifie en admin
    assert response.status_code in (403, 302)


def test_dashboard_200_pour_superuser():
    """GET /admin/bank-transfers/ -> 200 si superuser."""
    client, user = _login_as_admin()
    if not user.is_superuser:
        pytest.skip("L'admin de test n'est pas superuser, on teste le non-superuser dans test_dashboard_403")

    response = client.get('/admin/bank-transfers/')
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'bank-transfers-dashboard' in contenu


def test_create_403_pour_non_superuser():
    """POST /admin/bank-transfers/ -> 403 si pas superuser."""
    client, user = _login_as_admin()
    if user.is_superuser:
        pytest.skip("L'admin de test est superuser")

    response = client.post('/admin/bank-transfers/', data={
        'tenant_uuid': str(uuid_module.uuid4()),
        'asset_uuid': str(uuid_module.uuid4()),
        'montant_euros': '1.00',
        'date_virement': '2026-04-13',
        'reference': 'TEST',
    })
    assert response.status_code in (403, 302)


def test_historique_global_403_pour_non_superuser():
    """GET /admin/bank-transfers/historique/ -> 403 si pas superuser."""
    client, user = _login_as_admin()
    if user.is_superuser:
        pytest.skip("L'admin de test est superuser")

    response = client.get('/admin/bank-transfers/historique/')
    assert response.status_code in (403, 302)


def test_historique_tenant_accessible_pour_admin_tenant():
    """
    GET /admin/bank-transfers/historique-tenant/ -> 200 pour un admin tenant.
    Page lecture seule, pas de bouton de saisie.
    """
    client, user = _login_as_admin()
    response = client.get('/admin/bank-transfers/historique-tenant/')
    # Si l'admin est admin tenant : 200. Sinon 403.
    # Le user admin@admin.com est admin tenant lespass de toute facon (sinon il n'aurait pas acces a /admin/).
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'bank-transfers-historique' in contenu
    # Pas de bouton de saisie sur la vue tenant
    assert 'btn-saisir-virement' not in contenu


@pytest.fixture(scope="module", autouse=True)
def cleanup_admin_bt_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            wallets_test = Wallet.objects.filter(name__startswith=ADM_BT_TEST_PREFIX)
            assets_test = Asset.objects.filter(name__startswith=ADM_BT_TEST_PREFIX)
            Transaction.objects.filter(asset__in=assets_test).delete()
            assets_test.delete()
            wallets_test.delete()
    except Exception:
        pass
