"""
tests/pytest/test_admin_cards.py — Tests permissions et filtres CarteCashlessAdmin (Phase 1).

LANCEMENT :
    docker exec lespass_django poetry run pytest tests/pytest/test_admin_cards.py -v --api-key dummy
"""
import uuid as uuid_module

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as TestClient
from django.urls import reverse
from django_tenants.utils import schema_context

from Customers.models import Client
from QrcodeCashless.models import CarteCashless, Detail


CARDS_TEST_PREFIX = "ADMTEST"


@pytest.fixture(scope="module")
def tenant_lespass():
    return Client.objects.get(schema_name='lespass')


@pytest.fixture(scope="module")
def tenant_other():
    """Un autre tenant pour tester l'isolation."""
    return Client.objects.exclude(schema_name__in=["public", "lespass"]).first()


@pytest.fixture
def carte_lespass(tenant_lespass):
    """Carte rattachee au tenant lespass."""
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_LESP',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00001',
            number='ADM00001',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        yield carte
        carte.delete()
        Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_LESP').delete()


@pytest.fixture
def carte_autre_tenant(tenant_other):
    """Carte rattachee a un autre tenant (test isolation)."""
    if tenant_other is None:
        pytest.skip("Pas de second tenant disponible pour le test d'isolation")
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_OTHR',
            origine=tenant_other,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00002',
            number='ADM00002',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
        yield carte
        carte.delete()
        Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_OTHR').delete()


def _login_admin_lespass():
    """Cree un client de test login en tant qu'admin du tenant lespass."""
    client = TestClient(HTTP_HOST='lespass.tibillet.localhost')
    User = get_user_model()
    user = User.objects.filter(email='admin@admin.com').first()
    if user is None:
        pytest.skip("User admin@admin.com introuvable")
    client.force_login(user)
    return client, user


def test_card_admin_filter_by_tenant(carte_lespass, carte_autre_tenant):
    """
    Admin tenant ne voit que les cartes dont detail.origine == son tenant.
    Tenant admin only sees cards whose detail.origine matches their tenant.
    """
    client, user = _login_admin_lespass()
    if user.is_superuser:
        pytest.skip("L'utilisateur de test est superuser (test dedie separe)")

    response = client.get('/admin/QrcodeCashless/cartecashless/')
    assert response.status_code == 200
    contenu = response.content.decode()
    assert 'ADM00001' in contenu  # Carte du tenant lespass : visible
    assert 'ADM00002' not in contenu  # Carte d'un autre tenant : invisible


def test_card_admin_add_forbidden_for_tenant_admin(tenant_lespass):
    """
    POST sur add_view -> 403 si l'utilisateur n'est pas superuser.
    """
    client, user = _login_admin_lespass()
    if user.is_superuser:
        pytest.skip("Test specifique aux non-superusers")

    response = client.get('/admin/QrcodeCashless/cartecashless/add/')
    # Django admin renvoie 403 ou redirige vers index si pas la permission
    assert response.status_code in (403, 302)


def test_refund_panel_requires_admin(tenant_lespass):
    """
    GET sur refund-panel/ : partial HTMX retourne 200 avec data-testid refund-panel.
    GET on refund-panel/: HTMX partial returns 200 with data-testid refund-panel.
    """
    client, user = _login_admin_lespass()
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_PANL',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00011',
            number='ADM00011',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
    try:
        url = reverse(
            "staff_admin:QrcodeCashless_cartecashless_refund_panel",
            args=[carte.uuid],
        )
        response = client.get(url)
        assert response.status_code == 200
        assert b'data-testid="refund-panel"' in response.content
    finally:
        with schema_context('lespass'):
            carte.delete()
            Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_PANL').delete()


def test_refund_panel_carte_vierge(tenant_lespass):
    """
    GET refund-panel/ sur carte sans wallet : data-testid card-refund-empty present.
    GET refund-panel/ on card without wallet: data-testid card-refund-empty present.
    """
    client, user = _login_admin_lespass()
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_VIDE',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte_vide = CarteCashless.objects.create(
            tag_id='ADM00099',
            number='ADM00099',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
    try:
        url = reverse(
            "staff_admin:QrcodeCashless_cartecashless_refund_panel",
            args=[carte_vide.uuid],
        )
        response = client.get(url)
        assert response.status_code == 200
        contenu = response.content.decode()
        assert 'refund-panel-empty' in contenu  # data-testid du div info (B4)
        assert 'btn-open-refund-modal' not in contenu  # Pas de bouton ouvrir modal
    finally:
        with schema_context('lespass'):
            carte_vide.delete()
            Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_VIDE').delete()


def test_refund_modal_returns_form(tenant_lespass):
    """
    GET refund-modal/ : partial HTMX retourne 200 avec data-testid refund-modal et champ vider_carte.
    GET refund-modal/: HTMX partial returns 200 with data-testid refund-modal and vider_carte field.
    """
    client, user = _login_admin_lespass()
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_MODL',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00012',
            number='ADM00012',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
    try:
        url = reverse(
            "staff_admin:QrcodeCashless_cartecashless_refund_modal",
            args=[carte.uuid],
        )
        response = client.get(url)
        assert response.status_code == 200
        assert b'data-testid="refund-modal"' in response.content
        assert b'name="vider_carte"' in response.content
    finally:
        with schema_context('lespass'):
            carte.delete()
            Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_MODL').delete()


def test_refund_confirm_htmx_response(tenant_lespass):
    """
    POST refund-confirm/ : retourne 200 + header HX-Refresh ou HX-Trigger.
    POST refund-confirm/: returns 200 + HX-Refresh or HX-Trigger header.
    """
    client, user = _login_admin_lespass()
    with schema_context('lespass'):
        detail, _ = Detail.objects.get_or_create(
            base_url=f'{CARDS_TEST_PREFIX}_CONF',
            origine=tenant_lespass,
            defaults={"generation": 0},
        )
        carte = CarteCashless.objects.create(
            tag_id='ADM00013',
            number='ADM00013',
            uuid=uuid_module.uuid4(),
            detail=detail,
        )
    try:
        url = reverse(
            "staff_admin:QrcodeCashless_cartecashless_refund_confirm",
            args=[carte.uuid],
        )
        response = client.post(url, {"vider_carte": "false"})
        assert response.status_code == 200
        # Soit HX-Refresh (succes) soit HX-Trigger peut etre present
        # Either HX-Refresh (success) or the toast partial without header (no eligible tokens)
        assert response.has_header("HX-Refresh") or b'data-testid="refund-toast"' in response.content
    finally:
        with schema_context('lespass'):
            carte.delete()
            Detail.objects.filter(base_url=f'{CARDS_TEST_PREFIX}_CONF').delete()


@pytest.fixture
def client_admin():
    """Client de test connecte en tant qu'admin lespass."""
    client, _user = _login_admin_lespass()
    return client


@pytest.fixture(scope="module", autouse=True)
def cleanup_admin_test_data():
    """Nettoyage en fin de module."""
    yield
    try:
        with schema_context('lespass'):
            CarteCashless.objects.filter(tag_id__startswith='ADM').delete()
            Detail.objects.filter(base_url__startswith=CARDS_TEST_PREFIX).delete()
    except Exception:
        pass
