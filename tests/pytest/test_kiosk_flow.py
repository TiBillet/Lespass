"""
tests/pytest/test_kiosk_flow.py — Tests DEMO du parcours de recharge kiosque (CHANTIER-02, Tasks 02A + 02B).
tests/pytest/test_kiosk_flow.py — DEMO tests for the kiosk refill flow (CHANTIER-02, Tasks 02A + 02B).

Les tests refill_with_wisepos et list_renders (mockes) verifient que la bonne vue
est appelee sans exiger le rendu HTML complet. Le test test_kiosk_list_renders_select_amount_page_for_real
(Task 02B) rend reellement kiosk/select_amount.html (templates + static desormais crees)
et verifie un fragment HTML attendu, sans mocker render.
/ The refill_with_wisepos and list_renders (mocked) tests check the right view is called
without requiring the full HTML render. test_kiosk_list_renders_select_amount_page_for_real
(Task 02B) really renders kiosk/select_amount.html (templates + static now created)
and checks an expected HTML fragment, without mocking render.

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_flow.py -v --api-key dummy
"""

from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpResponse
from django.test import override_settings
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from kiosk.models import PaymentsIntent, Terminal

TEST_TAG_ID = "AAAA1111"


@pytest.fixture
def tenant():
    # Tenant de dev. Aligner le schema_name sur test_kiosk_models.py.
    return Client.objects.get(schema_name="lespass")


@pytest.fixture
def clean_kiosk(tenant):
    """Nettoie les objets TEST_ crees par ce module, avant ET apres.
    / Cleans up the TEST_ objects created by this module, before AND after."""
    def _clean():
        with tenant_context(tenant):
            PaymentsIntent.objects.filter(terminal__name__startswith="TEST_KIOSK_").delete()
            Terminal.objects.filter(name__startswith="TEST_KIOSK_").delete()
            CarteCashless.objects.filter(tag_id=TEST_TAG_ID).delete()
            TermUser.objects.filter(email="test-kiosk@tibillet.localhost").delete()
    _clean()
    yield
    _clean()


@pytest.fixture
def kiosk_user_and_terminal(tenant, clean_kiosk):
    """Un TermUser role Kiosque, appaire a un Terminal WisePOS via term_user.
    / A TermUser with the Kiosk role, paired to a WisePOS Terminal via term_user."""
    with tenant_context(tenant):
        user = TermUser.objects.create(
            email="test-kiosk@tibillet.localhost",
            username="test-kiosk@tibillet.localhost",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            is_active=True,
        )
        terminal = Terminal.objects.create(name="TEST_KIOSK_Borne1", term_user=user)
        return user, terminal


def _authenticated_client(user, tenant):
    """Client DRF authentifie par session (force_authenticate), route vers le tenant.
    / DRF client session-authenticated (force_authenticate), routed to the tenant."""
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["SERVER_NAME"] = f"{tenant.schema_name}.tibillet.localhost"
    return client


@pytest.mark.django_db
def test_kiosk_list_renders_select_amount_template(tenant, kiosk_user_and_terminal):
    """GET /kiosk/ rend bien kiosk/select_amount.html.
    / GET /kiosk/ renders kiosk/select_amount.html."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        with patch("kiosk.views.render") as mock_render:
            mock_render.return_value = HttpResponse(status=200)
            response = client.get("/kiosk/")

    assert response.status_code == 200
    template_name = mock_render.call_args[0][1]
    assert template_name == "kiosk/select_amount.html"


@pytest.mark.django_db
def test_kiosk_refill_with_wisepos_creates_payment_intent(tenant, kiosk_user_and_terminal):
    """POST /kiosk/refill_with_wisepos/ cree un PaymentsIntent et renvoie 200
    (Fedow, tache Celery et envoi au TPE Stripe mockes).
    / POST /kiosk/refill_with_wisepos/ creates a PaymentsIntent and returns 200
    (Fedow, Celery task and Stripe reader push are mocked)."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        CarteCashless.objects.create(tag_id=TEST_TAG_ID, number=TEST_TAG_ID)

        client = _authenticated_client(user, tenant)

        with patch("kiosk.validators.FedowAPI") as mock_fedow_api, \
             patch("kiosk.views.poll_payment_intent_status.delay") as mock_delay, \
             patch("kiosk.models.PaymentsIntent.send_to_terminal") as mock_send, \
             patch("kiosk.views.render") as mock_render:
            mock_fedow_api.return_value.NFCcard.retrieve.return_value = {"uuid": "fake"}
            mock_delay.return_value = MagicMock(status="STARTED", result=None)
            # send_to_terminal renvoie l'intention de paiement : on la relit en base
            # / send_to_terminal returns the payment intent: read it back from the DB
            mock_send.side_effect = lambda terminal_cible: PaymentsIntent.objects.get(
                terminal=terminal, amount=1000,
            )
            mock_render.return_value = HttpResponse(status=200)

            response = client.post("/kiosk/refill_with_wisepos/", data={
                "totalAmount": "10.00",
                "tag_id": TEST_TAG_ID,
            })

        assert response.status_code == 200
        assert PaymentsIntent.objects.filter(terminal=terminal, amount=1000).exists()
        template_name = mock_render.call_args[0][1]
        assert template_name == "kiosk/waiting_credit_card_terminal.html"


@pytest.mark.django_db
def test_kiosk_list_renders_select_amount_page_for_real(tenant, kiosk_user_and_terminal):
    """GET /kiosk/ rend reellement kiosk/select_amount.html (Task 02B : templates
    + static kiosk copies depuis LaBoutik). Pas de mock de render : on verifie
    que le HTML final contient bien le fragment attendu de la page.
    / GET /kiosk/ actually renders kiosk/select_amount.html (Task 02B: kiosk
    templates + static copied from LaBoutik). No render mock: checks the final
    HTML contains the expected page fragment."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "Sélectionnez le montant de la recharge souhaitée" in content
    assert 'id="tb-kiosque"' in content
    # Adaptation Task 02B : /htmx/kiosk/ -> /kiosk/ (SPEC), aucune URL LaBoutik ne doit subsister.
    # / Task 02B adaptation: /htmx/kiosk/ -> /kiosk/ (SPEC), no LaBoutik URL should remain.
    assert "/htmx/kiosk/" not in content


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_kiosk_demo_page_loads_nfc_and_socket_io_and_exposes_kiosk_context(tenant, kiosk_user_and_terminal):
    """CHANTIER-05 : en DEMO, le rendu de select_amount.html charge nfc.js ET
    socket.io (avant nfc.js), et expose window.DEMO + window.KIOSK (avec
    type_app) au JS.
    / CHANTIER-05: in DEMO, the select_amount.html render loads nfc.js AND
    socket.io (before nfc.js), and exposes window.DEMO + window.KIOSK (with
    type_app) to the JS."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/?type_app=cordova")

    assert response.status_code == 200
    content = response.content.decode()

    # socket.io charge avant nfc.js (necessaire au mode NFCLO)
    # / socket.io loaded before nfc.js (required for NFCLO mode)
    index_socket_io = content.index("js/socket.io.min.js")
    index_nfc_js = content.index("kiosk/js/nfc.js")
    assert index_socket_io < index_nfc_js

    # window.DEMO pose par base.html en DEMO, avec les 4 tags simulateur
    # / window.DEMO set by base.html in DEMO, with the 4 simulator tags
    assert "window.DEMO" in content
    assert "demoTagIdCm" in content
    assert "demoTagIdClient1" in content
    assert "demoTagIdClient2" in content
    assert "demoTagIdClient3" in content

    # window.KIOSK expose le type_app pour que nfc.js choisisse le mode hardware
    # (ici non utilise car DEMO force le simulateur, mais doit rester correct).
    # / window.KIOSK exposes type_app so nfc.js can pick the hardware mode
    # (unused here since DEMO forces the simulator, but must stay correct).
    assert "window.KIOSK" in content
    assert 'type_app: "cordova"' in content
    assert "demo: true" in content


@pytest.mark.django_db
@override_settings(DEMO=True)
def test_kiosk_demo_page_exposes_non_cordova_type_app_for_pi_mode(tenant, kiosk_user_and_terminal):
    """CHANTIER-05 : sans type_app=cordova (borne Pi/desktop), window.KIOSK.type_app
    n'est pas "cordova" : nfc.js choisira le mode NFCLO (socket.io local) plutot
    que NFCMC (plugin Cordova). Verifie au niveau contexte/rendu ; le clic
    simulateur reste un test manuel navigateur.
    / CHANTIER-05: without type_app=cordova (Pi/desktop kiosk), window.KIOSK.type_app
    is not "cordova": nfc.js will pick NFCLO mode (local socket.io) instead of
    NFCMC (Cordova plugin). Checked at context/render level; the simulator click
    remains a manual browser test."""
    user, terminal = kiosk_user_and_terminal
    with tenant_context(tenant):
        client = _authenticated_client(user, tenant)
        response = client.get("/kiosk/?type_app=pi")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'type_app: "pi"' in content
    # Pas de cordova.js injecte pour une cible Pi / no cordova.js injected for a Pi target
    assert "cordova.js" not in content
