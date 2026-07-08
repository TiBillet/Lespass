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
