"""
Tests de la page d'intégration iframe (embed) de réservation.
/ Tests for the booking embed iframe page.

LOCALISATION : booking/tests/test_embed.py

Ces tests couvrent uniquement ce qui est spécifique à la route /booking/embed/ :
- La route existe et répond 200 (nouvelle route non testée ailleurs).
- Le header X-Frame-Options autorise l'intégration iframe.
- Le chrome du site (navbar) est absent de la réponse.

La logique métier (créneaux, filtre tag, ressources grisées) est déjà
couverte par test_views_public.py — pas de duplication ici.

/ These tests cover only what is specific to /booking/embed/:
- The route exists and returns 200 (new route, not tested elsewhere).
- The X-Frame-Options header allows iframe embedding.
- The site chrome (navbar) is absent from the response.

Business logic (slots, tag filter, greyed-out resources) is already
covered by test_views_public.py — no duplication here.

Lancement / Run:
    docker exec lespass_django poetry run pytest \
        booking/tests/test_embed.py -v
"""
import sys
import os

sys.path.insert(0, '/DjangoFiles')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'TiBillet.settings')

import django
django.setup()

import pytest
from django.test import Client as DjangoClient


TENANT_SCHEMA  = 'lespass'
HOST           = 'lespass.tibillet.localhost'
URL_EMBED      = '/booking/embed/'


# ─── Fixtures de session (héritage conftest.py) ──────────────────────────────

@pytest.fixture(scope="session")
def django_db_setup():
    """Pas de création de test database — utilise la base dev existante.
    / Skip test database creation — use the existing dev database.
    """
    pass


@pytest.fixture(autouse=True, scope="session")
def _enable_db_access_for_all(django_db_blocker):
    """Désactiver le bloqueur d'accès DB de pytest-django.
    / Disable pytest-django's database blocker.
    """
    django_db_blocker.unblock()
    yield
    django_db_blocker.restore()


# ─── Fixture : client HTTP anonyme ───────────────────────────────────────────

@pytest.fixture(scope="module")
def client_anonyme():
    """
    Client Django anonyme (non authentifié) configuré pour le tenant lespass.
    / Anonymous (unauthenticated) Django test client configured for the lespass tenant.
    """
    return DjangoClient(HTTP_HOST=HOST)


# ─── Tests ──────────────────────────────────────────────────────────────────

def test_embed_page_accessible_without_authentication(client_anonyme):
    """
    La page embed est accessible sans authentification.
    / The embed page is accessible without authentication.

    LOCALISATION : booking/tests/test_embed.py

    La route /booking/embed/ doit retourner HTTP 200 pour un visiteur anonyme.
    / The /booking/embed/ route must return HTTP 200 for an anonymous visitor.
    """
    # Requête GET anonyme sur la page embed.
    # / Anonymous GET request on the embed page.
    reponse = client_anonyme.get(URL_EMBED)

    # La page doit répondre 200, pas 302 (redirect vers login).
    # / Page must respond 200, not 302 (redirect to login).
    assert reponse.status_code == 200


def test_embed_page_response_allows_iframe_embedding(client_anonyme):
    """
    La réponse de la page embed autorise l'intégration dans un iframe.
    / The embed page response allows embedding in an iframe.

    LOCALISATION : booking/tests/test_embed.py

    Le header X-Frame-Options doit être 'ALLOWALL' pour que les navigateurs
    autorisent l'intégration sur des sites externes (spec §4.4).
    / The X-Frame-Options header must be 'ALLOWALL' so browsers allow
    embedding on external sites (spec §4.4).
    """
    reponse = client_anonyme.get(URL_EMBED)

    assert reponse.status_code == 200

    # Le header X-Frame-Options doit autoriser l'iframe.
    # / The X-Frame-Options header must allow iframe embedding.
    valeur_header = reponse.get('X-Frame-Options', '')
    assert valeur_header == 'ALLOWALL', (
        f"X-Frame-Options attendu 'ALLOWALL', reçu '{valeur_header}'"
    )


def test_embed_page_has_no_site_navigation_chrome(client_anonyme):
    """
    La page embed ne contient pas le chrome de navigation du site.
    / The embed page does not contain the site navigation chrome.

    LOCALISATION : booking/tests/test_embed.py

    La navbar reunion possède id="mainMenu" (navbar.html ligne 16).
    Cet identifiant unique doit être absent de la réponse embed.
    / The reunion navbar has id="mainMenu" (navbar.html line 16).
    This unique identifier must be absent from the embed response.
    """
    reponse = client_anonyme.get(URL_EMBED)

    assert reponse.status_code == 200
    contenu = reponse.content.decode('utf-8')

    # La navbar (id="mainMenu") ne doit pas être présente dans l'embed.
    # / The navbar (id="mainMenu") must not be present in the embed.
    assert 'id="mainMenu"' not in contenu
