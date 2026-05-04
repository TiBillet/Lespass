"""
Tests du pont d'authentification hardware /laboutik/auth/bridge/.
/ Tests of the hardware auth bridge /laboutik/auth/bridge/.
"""
import uuid

import pytest
from django.test import Client
from django_tenants.utils import tenant_context

from AuthBillet.models import TermUser, TibilletUser
from BaseBillet.models import LaBoutikAPIKey
from Customers.models import Client as TenantClient


@pytest.fixture
def tenant_lespass():
    return TenantClient.objects.get(schema_name='lespass')


@pytest.fixture
def termuser_with_key(tenant_lespass):
    """Crée un TermUser Laboutik avec une clé API liée.
    / Creates a Laboutik TermUser with a linked API key."""
    with tenant_context(tenant_lespass):
        term_user = TermUser.objects.create(
            email=f'{uuid.uuid4()}@terminals.local',
            username=f'{uuid.uuid4()}@terminals.local',
            terminal_role='LB',
            accept_newsletter=False,
        )
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name='test-bridge',
            user=term_user,
        )
    yield term_user, api_key_string
    with tenant_context(tenant_lespass):
        term_user.delete()  # CASCADE supprime aussi la clé


@pytest.fixture
def orphan_api_key(tenant_lespass):
    """Crée une LaBoutikAPIKey sans user lié (V1 legacy).
    / Creates a LaBoutikAPIKey without linked user (V1 legacy)."""
    with tenant_context(tenant_lespass):
        _key, api_key_string = LaBoutikAPIKey.objects.create_key(
            name=f'test-v1-legacy-{uuid.uuid4().hex[:6]}',
            user=None,
        )
    yield api_key_string
    with tenant_context(tenant_lespass):
        LaBoutikAPIKey.objects.filter(name__startswith='test-v1-legacy-').delete()


def _post_bridge(api_key_string=None):
    """POST /laboutik/auth/bridge/ avec optionnel header Api-Key.
    / POST /laboutik/auth/bridge/ with optional Api-Key header."""
    # Le throttle anonyme limite à 10/min. cache.clear() efface TOUTES les clés
    # Django (pas seulement le throttle) : acceptable uniquement sur dev DB.
    # / Anonymous throttle limits to 10/min. cache.clear() wipes ALL Django
    # cache keys (not just throttle): acceptable only on dev DB.
    from django.core.cache import cache
    cache.clear()

    client = Client(HTTP_HOST='lespass.tibillet.localhost')
    headers = {}
    if api_key_string:
        headers['HTTP_AUTHORIZATION'] = f'Api-Key {api_key_string}'
    return client, client.post('/laboutik/auth/bridge/', **headers)


class TestHardwareAuthBridge:
    def test_bridge_avec_cle_valide_retourne_204(self, termuser_with_key):
        """Une clé valide retourne 204 No Content."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert response.status_code == 204

    def test_bridge_avec_cle_valide_pose_cookie_sessionid(self, termuser_with_key):
        """Le bridge pose un cookie sessionid sur la réponse."""
        _term_user, api_key = termuser_with_key
        _client, response = _post_bridge(api_key)
        assert 'sessionid' in response.cookies

    def test_bridge_sans_header_authorization_retourne_401(self):
        """Header absent → 401."""
        _client, response = _post_bridge(None)
        assert response.status_code == 401

    def test_bridge_avec_cle_invalide_retourne_401(self):
        """Clé inexistante → 401."""
        _client, response = _post_bridge('AAAAAA.BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB')
        assert response.status_code == 401

    def test_bridge_avec_cle_sans_user_retourne_400(self, orphan_api_key):
        """Clé V1 (user=None) → 400 avec message explicite."""
        _client, response = _post_bridge(orphan_api_key)
        assert response.status_code == 400
        assert b'Legacy' in response.content or b'legacy' in response.content

    def test_bridge_avec_user_revoque_retourne_401(self, termuser_with_key, tenant_lespass):
        """TermUser.is_active=False → 401."""
        term_user, api_key = termuser_with_key
        with tenant_context(tenant_lespass):
            term_user.is_active = False
            term_user.save()
        _client, response = _post_bridge(api_key)
        assert response.status_code == 401

    def test_bridge_avec_get_retourne_405(self, termuser_with_key):
        """GET sur l'endpoint → 405 Method Not Allowed."""
        _term_user, api_key = termuser_with_key
        from django.core.cache import cache
        cache.clear()
        client = Client(HTTP_HOST='lespass.tibillet.localhost')
        response = client.get(
            '/laboutik/auth/bridge/',
            HTTP_AUTHORIZATION=f'Api-Key {api_key}',
        )
        assert response.status_code == 405

    def test_apres_bridge_requete_metier_passe_avec_cookie(self, termuser_with_key):
        """Flow E2E : bridge → GET /laboutik/caisse/ → 200 ou 302."""
        _term_user, api_key = termuser_with_key
        client, response_bridge = _post_bridge(api_key)
        assert response_bridge.status_code == 204

        # Le client a maintenant son cookie sessionid automatiquement
        response_caisse = client.get('/laboutik/caisse/')
        # 200 OK ou 302 (redirect vers sélection PV) = auth a passé
        assert response_caisse.status_code in (200, 302)

    def test_bridge_permet_acces_paiement_viewset_cookie_only(self, termuser_with_key):
        """
        Après bridge, le cookie seul (sans header Api-Key) doit passer sur
        PaiementViewSet (migré V2). Verrou contre régression : si un futur
        refactor remet PaiementViewSet sur V1, le cookie-only échouera.
        / After bridge, cookie alone (no Api-Key header) must work on
        PaiementViewSet (V2-migrated). Locks contract: if a future refactor
        reverts PaiementViewSet to V1, cookie-only will fail.
        """
        _term_user, api_key = termuser_with_key
        client, response_bridge = _post_bridge(api_key)
        assert response_bridge.status_code == 204

        # On frappe un endpoint de PaiementViewSet. L'URL exacte dépend du router,
        # on cible la route de base /laboutik/paiement/ qui doit au moins répondre
        # 200 / 302 / 405 (pas 401/403) si l'auth passe.
        # / Hit a PaiementViewSet endpoint. Exact URL depends on router, but
        # /laboutik/paiement/ should respond 200/302/405 (not 401/403) if auth OK.
        response_paiement = client.get('/laboutik/paiement/')
        # On exclut explicitement les codes d'auth refusée
        # / Explicitly exclude auth-refused codes
        assert response_paiement.status_code not in (401, 403), (
            f"Cookie-only rejected by PaiementViewSet: "
            f"{response_paiement.status_code}. Check that PaiementViewSet "
            f"uses HasLaBoutikTerminalAccess."
        )


class TestHasLaBoutikTerminalAccess:
    """Tests directs de la permission (sans HTTP) / Direct permission tests."""

    def test_permission_accepte_termuser_role_LB_du_tenant(self, termuser_with_key, tenant_lespass):
        """TermUser LB du bon tenant → accès accordé."""
        from unittest.mock import Mock
        from BaseBillet.permissions import HasLaBoutikTerminalAccess

        term_user, _api_key = termuser_with_key
        with tenant_context(tenant_lespass):
            request = Mock()
            request.user = term_user
            request.META = {}
            perm = HasLaBoutikTerminalAccess()
            assert perm.has_permission(request, None) is True

    def test_permission_refuse_termuser_role_TI(self, tenant_lespass):
        """
        TermUser rôle Tireuse → pas d'accès Laboutik.
        Le fallback V1 (HasLaBoutikAccess) refuse avec PermissionDenied
        car l'utilisateur n'est pas tenant_admin et qu'il n'y a pas de clé API.
        / TI-role TermUser → no LaBoutik access.
        V1 fallback raises PermissionDenied (not tenant_admin, no API key).
        """
        import pytest
        from unittest.mock import Mock
        from BaseBillet.permissions import HasLaBoutikTerminalAccess
        from rest_framework.exceptions import PermissionDenied

        with tenant_context(tenant_lespass):
            tireuse_user = TermUser.objects.create(
                email=f'tireuse-{uuid.uuid4()}@terminals.local',
                username=f'tireuse-{uuid.uuid4()}@terminals.local',
                terminal_role='TI',
            )
            try:
                request = Mock()
                request.user = tireuse_user
                request.META = {}
                perm = HasLaBoutikTerminalAccess()
                with pytest.raises(PermissionDenied):
                    perm.has_permission(request, None)
            finally:
                tireuse_user.delete()

    def test_permission_refuse_termuser_LB_autre_tenant(self, tenant_lespass):
        """
        TermUser LB d'un AUTRE tenant → refus côté V2 (isolation cross-tenant).
        Le fallback V1 refuse aussi car le TermUser n'est pas admin ici.
        / LB TermUser from ANOTHER tenant → V2 refusal (cross-tenant isolation).
        V1 fallback also refuses (TermUser is not admin here).
        """
        import pytest
        from unittest.mock import Mock
        from BaseBillet.permissions import HasLaBoutikTerminalAccess
        from rest_framework.exceptions import PermissionDenied
        from Customers.models import Client as TenantClient

        # On cherche un tenant DIFFÉRENT de lespass pour créer un TermUser dessus
        # / Find a tenant DIFFERENT from lespass to create a TermUser on
        autre_tenant = TenantClient.objects.exclude(
            schema_name__in=('public', 'lespass'),
        ).first()

        if autre_tenant is None:
            pytest.skip("Aucun autre tenant disponible pour tester cross-tenant")

        # Créer un TermUser LB dans l'autre tenant
        # / Create a LB TermUser on the other tenant
        with tenant_context(autre_tenant):
            foreign_user = TermUser.objects.create(
                email=f'foreign-{uuid.uuid4()}@terminals.local',
                username=f'foreign-{uuid.uuid4()}@terminals.local',
                terminal_role='LB',
            )

        try:
            # On évalue la permission dans le contexte de LESPASS
            # / We evaluate the permission in the LESPASS tenant context
            with tenant_context(tenant_lespass):
                request = Mock()
                request.user = foreign_user
                request.META = {}
                perm = HasLaBoutikTerminalAccess()
                # Doit lever PermissionDenied (V2 refuse via client_source, V1 aussi)
                # / Must raise PermissionDenied (V2 refuses via client_source, V1 too)
                with pytest.raises(PermissionDenied):
                    perm.has_permission(request, None)
        finally:
            with tenant_context(autre_tenant):
                foreign_user.delete()


def test_fixture_terminal_client_fonctionne(terminal_client):
    """
    Smoke test de la fixture terminal_client.
    Vérifie que le client authentifié peut accéder à /laboutik/caisse/.
    La validation réelle de la permission HasLaBoutikTerminalAccess est
    couverte par les tests dédiés dans TestHasLaBoutikTerminalAccess.
    / Smoke test of the terminal_client fixture.
    Checks that the authenticated client can access /laboutik/caisse/.
    Actual HasLaBoutikTerminalAccess permission validation is covered
    by TestHasLaBoutikTerminalAccess.
    """
    # Le client est authentifié, on peut faire une requête
    # / Client is authenticated, we can make a request
    response = terminal_client.get('/laboutik/caisse/')

    # On accepte 200 ou 302 (redirect vers sélection PV),
    # mais PAS un redirect vers /login (qui signalerait une auth cassée).
    # / We accept 200 or 302 (redirect to PV selection),
    # but NOT a redirect to /login (which would mean broken auth).
    assert response.status_code in (200, 302)
    if response.status_code == 302:
        assert '/login' not in response.url.lower(), (
            f"Redirection vers login = auth cassée: {response.url}"
        )
