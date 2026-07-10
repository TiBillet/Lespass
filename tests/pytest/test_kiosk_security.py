"""
tests/pytest/test_kiosk_security.py — Garde central des sessions terminal.
tests/pytest/test_kiosk_security.py — Central terminal-session guard.

Un TermUser (espece=TE, borne kiosk / caisse) est authentifie via le bridge, mais
n'est PAS un humain. Le middleware AuthBillet.middleware.TerminalSessionGuardMiddleware
le restreint a son interface (/kiosk/, /laboutik/, /controlvanne/) et le renvoie
vers son accueil s'il tente une vue humaine (/my_account/, /, ...).
Un admin du tenant (humain) peut, lui, ouvrir /kiosk/ depuis un navigateur (demo/debug).
/ A TermUser is authenticated via the bridge but is not a human: the middleware
restricts it to its interface and redirects it home otherwise. A tenant admin
(human) can still open /kiosk/ from a browser.

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_security.py -v --api-key dummy
"""

import uuid
from unittest.mock import patch

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, HumanUser, TibilletUser
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant():
    return TenantClient.objects.get(schema_name="lespass")


@pytest.fixture
def kiosk_terminal(tenant):
    """Un TermUser role Kiosque (espece TE). / A Kiosk-role TermUser (espece TE)."""
    with tenant_context(tenant):
        term = TermUser.objects.create(
            email=f"{uuid.uuid4()}@terminals.local",
            username=f"{uuid.uuid4()}@terminals.local",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            accept_newsletter=False,
        )
    yield term
    with tenant_context(tenant):
        term.delete()


def _client():
    return Client(HTTP_HOST="lespass.tibillet.localhost")


@pytest.mark.django_db
def test_terminal_redirige_hors_de_son_interface(kiosk_terminal):
    """Le garde central renvoie un terminal vers /kiosk/ des qu'il sort de son interface.
    / The guard redirects a terminal to /kiosk/ whenever it leaves its interface."""
    client = _client()
    client.force_login(kiosk_terminal)

    # Vue humaine « mon compte » -> redirige vers l'interface du terminal.
    # / Human account view -> redirected to the terminal interface.
    response_compte = client.get("/my_account/")
    assert response_compte.status_code == 302
    assert response_compte.url == "/kiosk/"

    # Accueil public -> egalement redirige. / Public home -> also redirected.
    response_accueil = client.get("/")
    assert response_accueil.status_code == 302
    assert response_accueil.url == "/kiosk/"


@pytest.mark.django_db
def test_terminal_accede_a_son_interface(kiosk_terminal):
    """Un terminal Kiosque accede bien a /kiosk/ (whitelist du garde central).
    / A Kiosk terminal reaches /kiosk/ (guard whitelist)."""
    client = _client()
    client.force_login(kiosk_terminal)
    response = client.get("/kiosk/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_humain_peut_ouvrir_le_kiosk(tenant):
    """Un admin du tenant (humain) peut ouvrir /kiosk/ depuis un navigateur (demo/debug).
    / A tenant admin (human) can open /kiosk/ from a browser (demo/debug)."""
    with tenant_context(tenant):
        admin = HumanUser.objects.create(
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            username=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        )
        admin.client_admin.add(tenant)  # devient admin du tenant / becomes tenant admin
    try:
        client = _client()
        client.force_login(admin)
        response = client.get("/kiosk/")
        assert response.status_code == 200
    finally:
        with tenant_context(tenant):
            admin.delete()


@pytest.mark.django_db
def test_admin_refuse_sur_le_kiosk_hors_demo_debug(tenant, settings):
    """Hors demo/debug, un admin ne peut PLUS ouvrir /kiosk/ par navigateur.
    En production, une borne kiosk est un appareil physique : seule une vraie
    borne appairee y accede.
    / Outside demo/debug, an admin can no longer open /kiosk/ by browser."""
    settings.DEBUG = False
    settings.DEMO = False
    with tenant_context(tenant):
        admin = HumanUser.objects.create(
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            username=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        )
        admin.client_admin.add(tenant)
    try:
        client = _client()
        client.force_login(admin)
        response = client.get("/kiosk/")
        # 403 (permission refusee) et non 200. Le garde terminal peut aussi
        # rediriger : on verifie surtout que ce n'est PAS un acces 200.
        # / 403, not 200. What matters is it is NOT a 200 access.
        assert response.status_code != 200
    finally:
        with tenant_context(tenant):
            admin.delete()


@pytest.mark.django_db
def test_humain_non_bloque_par_le_garde_terminal(tenant):
    """Un humain n'est PAS renvoye vers /kiosk/ par le garde terminal sur /my_account/.
    / A human is NOT bounced to /kiosk/ by the terminal guard on /my_account/.

    On mocke FedowAPI (creation de wallet) pour eviter tout appel reseau Fedow.
    / We mock FedowAPI (wallet creation) to avoid any Fedow network call."""
    with tenant_context(tenant):
        human = HumanUser.objects.create(
            email=f"human_{uuid.uuid4().hex[:8]}@example.com",
            username=f"human_{uuid.uuid4().hex[:8]}@example.com",
        )
    try:
        client = _client()
        client.force_login(human)
        with patch("BaseBillet.views.FedowAPI"):
            response = client.get("/my_account/")
        assert not (response.status_code == 302 and response.get("Location") == "/kiosk/")
    finally:
        with tenant_context(tenant):
            human.delete()


@pytest.fixture
def deux_bornes_et_un_paiement(tenant):
    """Deux bornes Kiosque appairees (A et B) + un PaymentsIntent appartenant a B.

    Sert a verifier qu'une borne ne peut pas agir sur le paiement d'une autre
    (IDOR intra-tenant). Le paiement est SUCCEEDED pour que payment_status
    reponde sans appeler Stripe (statut deja terminal).
    / Two paired Kiosk devices + a PaymentsIntent owned by B, to check a device
    cannot act on another's payment. SUCCEEDED so payment_status skips Stripe.
    """
    from kiosk.models import Terminal, PaymentsIntent

    with tenant_context(tenant):
        borne_a = TermUser.objects.create(
            email=f"{uuid.uuid4()}@terminals.local",
            username=f"{uuid.uuid4()}@terminals.local",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            accept_newsletter=False,
        )
        borne_b = TermUser.objects.create(
            email=f"{uuid.uuid4()}@terminals.local",
            username=f"{uuid.uuid4()}@terminals.local",
            terminal_role=TibilletUser.ROLE_KIOSQUE,
            accept_newsletter=False,
        )
        terminal_a = Terminal.objects.create(name="TPE A", term_user=borne_a, stripe_id="tmr_a")
        terminal_b = Terminal.objects.create(name="TPE B", term_user=borne_b, stripe_id="tmr_b")
        paiement_de_b = PaymentsIntent.objects.create(
            terminal=terminal_b,
            amount=500,
            payment_intent_stripe_id=f"pi_test_{uuid.uuid4().hex[:12]}",
            status=PaymentsIntent.SUCCEEDED,
        )
    yield {"borne_a": borne_a, "borne_b": borne_b, "paiement_de_b": paiement_de_b}
    with tenant_context(tenant):
        paiement_de_b.delete()
        terminal_a.delete()
        terminal_b.delete()
        borne_a.delete()
        borne_b.delete()


@pytest.mark.django_db
def test_payment_status_refuse_une_autre_borne(deux_bornes_et_un_paiement):
    """Une borne ne peut pas lire le statut du paiement d'une AUTRE borne (IDOR).
    / A device cannot read another device's payment status (IDOR)."""
    client = _client()
    client.force_login(deux_bornes_et_un_paiement["borne_a"])

    pk_du_paiement_de_b = deux_bornes_et_un_paiement["paiement_de_b"].pk
    response = client.get(f"/kiosk/{pk_du_paiement_de_b}/status/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_cancel_refuse_une_autre_borne(deux_bornes_et_un_paiement):
    """Une borne ne peut pas annuler le paiement en cours d'une AUTRE borne (IDOR).
    Le refus (404) survient AVANT tout appel Stripe, donc pas besoin de mock.
    / A device cannot cancel another device's payment. The 404 happens before any
    Stripe call, so no mock is needed."""
    client = _client()
    client.force_login(deux_bornes_et_un_paiement["borne_a"])

    pk_du_paiement_de_b = deux_bornes_et_un_paiement["paiement_de_b"].pk
    response = client.get(f"/kiosk/{pk_du_paiement_de_b}/cancel/")
    assert response.status_code == 404


@pytest.mark.django_db
def test_payment_status_borne_proprietaire_ok(deux_bornes_et_un_paiement):
    """La borne proprietaire lit bien le statut de SON paiement (ecran de succes).
    / The owning device does read ITS payment status (success screen)."""
    client = _client()
    client.force_login(deux_bornes_et_un_paiement["borne_b"])

    pk_du_paiement_de_b = deux_bornes_et_un_paiement["paiement_de_b"].pk
    response = client.get(f"/kiosk/{pk_du_paiement_de_b}/status/")
    assert response.status_code == 200
    assert b"tb-kiosque" in response.content
