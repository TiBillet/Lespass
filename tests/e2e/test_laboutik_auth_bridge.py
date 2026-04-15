"""
Test E2E Playwright du flow hardware bridge.
/ Playwright E2E test of the hardware bridge flow.

LOCALISATION : tests/e2e/test_laboutik_auth_bridge.py

Simule le comportement du client Android (Cordova WebView) :
1. POST /laboutik/auth/bridge/ avec header Authorization: Api-Key via fetch()
   dans le contexte de la page (cookie jar du navigateur)
2. Vérifie status 204 et cookie sessionid posé sur le WebView
3. Navigue vers /laboutik/caisse/ — le cookie session suffit pour passer l'auth
   (plus besoin du header Api-Key pour les pages suivantes)
/ Simulates the Android (Cordova WebView) client flow:
1. POST /laboutik/auth/bridge/ with Authorization: Api-Key via fetch() in the
   page context (browser cookie jar)
2. Verify 204 status and sessionid cookie set on WebView
3. Navigate to /laboutik/caisse/ — cookie session grants access
   (no Api-Key header needed for subsequent pages)

Prerequis / Prerequisites:
- Serveur Django actif via Traefik (lespass.tibillet.localhost)
- Tenant 'lespass' configuré avec LaBoutikAPIKey + TermUser
"""

import uuid

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _setup_termuser_with_key(django_shell, email_tag):
    """Crée un TermUser Laboutik avec une clé API liée dans le tenant lespass.
    Retourne la clé API en clair (visible une seule fois à la création).
    / Creates a Laboutik TermUser with linked API key in the lespass tenant.
    Returns the plaintext API key (only visible once at creation).
    """
    email = f"e2e-bridge-{email_tag}@terminals.local"
    # django_shell exécute du code dans le tenant 'lespass' (schema_name)
    # On imprime la clé avec un marqueur pour la parser.
    # / django_shell runs code in the 'lespass' tenant (schema_name).
    # We print the key with a marker to parse it.
    result = django_shell(
        "from AuthBillet.models import TermUser\n"
        "from BaseBillet.models import LaBoutikAPIKey\n"
        f"email = '{email}'\n"
        "term = TermUser.objects.create(email=email, username=email, terminal_role='LB', accept_newsletter=False)\n"
        "_, api_key_string = LaBoutikAPIKey.objects.create_key(name='e2e-bridge-test', user=term)\n"
        "print(f'API_KEY={api_key_string}')"
    )
    # Parser la clé / Parse the key
    for line in result.splitlines():
        if line.startswith("API_KEY="):
            return email, line[len("API_KEY="):].strip()
    pytest.fail(f"Could not parse API_KEY from django_shell output: {result}")


def _cleanup_termuser(django_shell, email):
    """Supprime le TermUser de test (CASCADE supprime la clé associée).
    / Deletes the test TermUser (CASCADE removes the linked key).
    """
    django_shell(
        "from AuthBillet.models import TermUser\n"
        f"TermUser.objects.filter(email='{email}').delete()\n"
        "print('CLEANUP_OK')"
    )


def test_flow_bridge_puis_caisse(page, django_shell):
    """
    Simule le flow complet : bridge (fetch header) → cookie → caisse accessible.
    / Full flow simulation: bridge via fetch+header → cookie → caisse accessible.
    """
    # Setup : TermUser + clé API dans le tenant lespass
    # Suffixe unique par run pour éviter collisions entre tests/runs.
    # / Setup: TermUser + API key in lespass tenant.
    # Unique suffix per run to avoid collisions between tests/runs.
    email_tag = uuid.uuid4().hex[:8]
    email, api_key_string = _setup_termuser_with_key(django_shell, email_tag)

    try:
        # Step 1 : charger une page sur lespass.tibillet.localhost
        # pour que le WebView ait un contexte cookie valide (origine définie).
        # / Step 1: load a page on lespass.tibillet.localhost so the WebView
        # has a valid cookie context (origin defined).
        page.goto("/")
        page.wait_for_load_state("domcontentloaded")

        # Step 2 : POST bridge via fetch dans la page (simule Cordova WebView)
        # Le fetch s'exécute dans l'origine de la page → cookie posé sur le context.
        # / Step 2: POST bridge via in-page fetch (simulates Cordova WebView)
        # fetch runs in the page origin → cookie set on the context.
        result = page.evaluate(
            """async (args) => {
                const response = await fetch(args.url, {
                    method: 'POST',
                    headers: { 'Authorization': `Api-Key ${args.key}` },
                    credentials: 'include',
                });
                return { status: response.status };
            }""",
            {"url": "/laboutik/auth/bridge/", "key": api_key_string},
        )

        assert result["status"] == 204, (
            f"Bridge expected 204, got {result['status']}. "
            "Check that TermUser is active, api_key linked, and tenant routing is OK."
        )

        # Vérifier qu'un cookie sessionid est bien posé sur le context.
        # / Verify a sessionid cookie is set on the context.
        cookies = page.context.cookies()
        session_cookies = [c for c in cookies if c["name"] == "sessionid"]
        assert session_cookies, (
            f"No sessionid cookie posted by bridge. Cookies: "
            f"{[c['name'] for c in cookies]}"
        )

        # Step 3 : naviguer vers /laboutik/caisse/ — le cookie posé par le bridge
        # doit permettre l'accès sans header. La page "ask primary card" doit
        # répondre 200 (HasLaBoutikTerminalAccess accepte le TermUser en session).
        # / Step 3: navigate to /laboutik/caisse/ — cookie from bridge
        # should grant access without a header. The "ask primary card" page
        # must return 200 (HasLaBoutikTerminalAccess accepts session TermUser).
        response = page.goto("/laboutik/caisse/")
        assert response is not None, "No response from /laboutik/caisse/"
        assert response.status == 200, (
            f"Expected 200 on /laboutik/caisse/, got {response.status}. "
            "The bridge session should grant HasLaBoutikTerminalAccess."
        )

        # Vérifier qu'on n'est pas redirigé vers login et pas d'erreur visible.
        # / Verify not redirected to login and no error shown.
        current_url = page.url
        assert "/login" not in current_url.lower(), (
            f"Redirected to login: {current_url}"
        )
        content = page.content()
        assert "Unauthorized" not in content
        assert "401" not in content or "caisse" in content.lower()
    finally:
        # Cleanup : supprime le TermUser + clé (CASCADE)
        # / Cleanup: delete TermUser + key (CASCADE)
        _cleanup_termuser(django_shell, email)
