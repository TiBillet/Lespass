"""
Tests du pont d'authentification hardware /laboutik/auth/bridge/.

Contrat COURANT de la vue (différent de lespass-main) :
- POST form-data `api_key=<key>` (pas de header Authorization)
- succès → 302 HttpResponseRedirect vers /laboutik/caisse + cookie sessionid
- clé legacy V1 (user=None) → 400 message explicite
- clé absente / invalide / user révoqué → 401

/ Tests of the hardware auth bridge (current contract: POST form-data api_key,
302 redirect on success, 400 for legacy keys, 401 otherwise).
"""
import sys

sys.path.insert(0, '/DjangoFiles')

import django

django.setup()

import uuid

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant_lespass():
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def termuser_with_key(tenant_lespass):
    """TermUser LaBoutik + clé API liée.
    / LaBoutik TermUser + linked API key."""
    with tenant_context(tenant_lespass):
        term_user = TermUser.objects.create(
            email=f'{uuid.uuid4()}@terminals.local',
            username=f'{uuid.uuid4()}@terminals.local',
            terminal_role='LB',
            accept_newsletter=False,
        )
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name=f'test-bridge-{uuid.uuid4().hex[:6]}',
            user=term_user,
        )
    yield term_user, api_key_string
    with tenant_context(tenant_lespass):
        term_user.delete()  # CASCADE supprime aussi la clé / CASCADE deletes the key


@pytest.fixture
def orphan_api_key(tenant_lespass):
    """Clé V1 legacy sans user lié.
    / Legacy V1 key without linked user."""
    with tenant_context(tenant_lespass):
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name=f'test-v1-legacy-{uuid.uuid4().hex[:6]}',
            user=None,
        )
    yield api_key_string
    with tenant_context(tenant_lespass):
        LaBoutikAPIKey.objects.filter(name__startswith='test-v1-legacy-').delete()


def _post_bridge(api_key_string=None):
    """POST form-data api_key sur le bridge (contrat courant).
    / POST form-data api_key on the bridge (current contract)."""
    # BridgeThrottle limite les tentatives ; cache.clear() le remet à zéro.
    # cache.clear() vide TOUT le cache Django : acceptable sur DB de dev seulement.
    # / BridgeThrottle limits attempts; cache.clear() resets it (wipes ALL Django
    # cache — acceptable only on dev DB).
    from django.core.cache import cache
    cache.clear()

    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    data = {}
    if api_key_string is not None:
        data['api_key'] = api_key_string
    return client, client.post('/laboutik/auth/bridge/', data=data)


class TestHardwareAuthBridge:
    def test_cle_valide_redirige_302(self, termuser_with_key):
        """Clé liée à un TermUser → 302 vers /laboutik/caisse."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert response.status_code == 302
        assert '/laboutik/caisse' in response.url

    def test_cle_valide_pose_cookie_sessionid(self, termuser_with_key):
        """Le bridge pose un cookie sessionid sur la réponse."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert 'sessionid' in response.cookies

    def test_sans_api_key_retourne_401(self):
        """Pas d'api_key dans le POST → 401."""
        _client, response = _post_bridge(None)
        assert response.status_code == 401

    def test_cle_invalide_retourne_401(self):
        """Clé inexistante → 401."""
        _client, response = _post_bridge('AAAAAA.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB')
        assert response.status_code == 401

    def test_cle_legacy_sans_user_retourne_400(self, orphan_api_key):
        """Clé V1 (user=None) → 400 explicite, PLUS de 500 AttributeError.

        C'est le test de non-régression du bug d'origine
        ('LaBoutikAPIKey' object has no attribute 'user').
        / Non-regression test for the original AttributeError bug.
        """
        _client, response = _post_bridge(orphan_api_key)
        assert response.status_code == 400
        assert b'Legacy' in response.content or b'legacy' in response.content

    def test_user_revoque_retourne_401(self, termuser_with_key, tenant_lespass):
        """TermUser.is_active=False → 401."""
        term_user, api_key = termuser_with_key
        with tenant_context(tenant_lespass):
            term_user.is_active = False
            term_user.save()
        _client, response = _post_bridge(api_key)
        assert response.status_code == 401
