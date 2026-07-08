"""
tests/pytest/test_kiosk_branchements.py — Tests des branchements du module kiosk (CHANTIER-03).
tests/pytest/test_kiosk_branchements.py — Tests for the kiosk module wiring (CHANTIER-03).

Verifie les 4 branchements :
1. Configuration.module_kiosk existe, defaut False.
2/3. MODULE_FIELDS + sidebar sont verifies visuellement (Playwright), pas ici.
4. Le bridge LaBoutik route un TermUser role Kiosque (KI) vers /kiosk/ et un
   TermUser role LaBoutik (LB) vers /laboutik/caisse (non-regression).
/ Checks the 4 wirings:
1. Configuration.module_kiosk exists, defaults to False.
2/3. MODULE_FIELDS + sidebar are checked visually (Playwright), not here.
4. The LaBoutik bridge routes a Kiosk-role (KI) TermUser to /kiosk/ and a
   LaBoutik-role (LB) TermUser to /laboutik/caisse (non-regression).

Lancement / Run:
    docker exec lespass_django poetry run pytest /DjangoFiles/tests/pytest/test_kiosk_branchements.py -v --api-key dummy
"""

import uuid

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import Configuration, LaBoutikAPIKey
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant():
    return TenantClient.objects.get(schema_name="lespass")


@pytest.mark.django_db
def test_module_kiosk_existe_et_defaut_false(tenant):
    """Configuration.module_kiosk existe et vaut False par defaut.
    / Configuration.module_kiosk exists and defaults to False."""
    with tenant_context(tenant):
        configuration = Configuration.get_solo()
        assert hasattr(configuration, "module_kiosk")
        assert configuration.module_kiosk is False


@pytest.fixture
def termuser_with_key(tenant):
    """TermUser + clé API liée, role parametrable via `terminal_role`.
    / TermUser + linked API key, role settable via `terminal_role`."""
    created = {}

    def _make(terminal_role):
        with tenant_context(tenant):
            term_user = TermUser.objects.create(
                email=f"{uuid.uuid4()}@terminals.local",
                username=f"{uuid.uuid4()}@terminals.local",
                terminal_role=terminal_role,
                accept_newsletter=False,
            )
            _key, api_key_string = LaBoutikAPIKey.objects.create_key(
                name=f"test-bridge-kiosk-{uuid.uuid4().hex[:6]}",
                user=term_user,
            )
        created["term_user"] = term_user
        return term_user, api_key_string

    yield _make

    if created.get("term_user"):
        with tenant_context(tenant):
            created["term_user"].delete()  # CASCADE supprime aussi la clé


def _post_bridge(api_key_string):
    """POST form-data api_key sur le bridge.
    / POST form-data api_key on the bridge."""
    from django.core.cache import cache

    cache.clear()  # remet a zero le throttle (BridgeThrottle)

    client = Client(HTTP_HOST="lespass.tibillet.localhost")
    return client, client.post(
        "/laboutik/auth/bridge/", data={"api_key": api_key_string}
    )


@pytest.mark.django_db
def test_bridge_role_kiosque_redirige_vers_kiosk(termuser_with_key):
    """Un TermUser role Kiosque (KI) est redirige vers /kiosk/.
    / A Kiosk-role (KI) TermUser is redirected to /kiosk/."""
    _term_user, api_key = termuser_with_key(TibilletUser.ROLE_KIOSQUE)
    _client, response = _post_bridge(api_key)
    assert response.status_code == 302
    assert response.url.startswith("/kiosk/")


@pytest.mark.django_db
def test_bridge_role_laboutik_redirige_vers_caisse(termuser_with_key):
    """Non-regression : un TermUser role LaBoutik (LB) reste redirige vers /laboutik/caisse.
    / Non-regression: a LaBoutik-role (LB) TermUser still redirects to /laboutik/caisse."""
    _term_user, api_key = termuser_with_key("LB")
    _client, response = _post_bridge(api_key)
    assert response.status_code == 302
    assert "/laboutik/caisse" in response.url
