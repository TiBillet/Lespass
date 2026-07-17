"""
Tests du squelette OnboardViewSet (Task 9 + refactor Task 10).
/ Tests for the OnboardViewSet scaffold (Task 9 + Task 10 refactor).

LOCALISATION: onboard/tests/test_viewset.py

On verifie :
  1. Les helpers de session (_get_or_none_wc / _set_session_wc /
     _clear_session_wc) font bien un round-trip via la session Django.
  2. La route racine `/onboard/` redirige (302) vers `onboard-identity`
     quand aucun brouillon n'est en session. Cette redirection a ete
     activee par le refactor de la Task 10 (avant : placeholder 200).

/ We verify:
  1. Session helpers do a clean round-trip via Django's session.
  2. The `/onboard/` root route redirects (302) to `onboard-identity`
     when no draft is in session. This redirect was enabled by the
     Task 10 refactor (before: 200 placeholder).
"""

from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from MetaBillet.models import WaitingConfiguration

from onboard.views import (
    SESSION_KEY,
    _clear_session_wc,
    _get_or_none_wc,
    _set_session_wc,
    OnboardViewSet,
)


def _make_request_with_session(method="get", path="/onboard/"):
    """
    Construit une request Django avec un SessionStore reel (DB) attache.
    On ne sauvegarde PAS la session en DB : les helpers manipulent juste
    `request.session` en memoire.
    / Build a Django request with a real DB-backed SessionStore attached.
    We do NOT persist the session: helpers only touch `request.session`
    in memory.
    """
    factory = RequestFactory()
    builder = getattr(factory, method)
    request = builder(path)
    request.session = SessionStore()
    return request


def test_session_helpers_round_trip(cleanup_waiting_configs):
    """
    Round-trip _set / _get / _clear sur un WaitingConfiguration reel.
    / Round-trip _set / _get / _clear with a real WaitingConfiguration.
    """
    # Cree un brouillon minimal (champs obligatoires uniquement) dans le
    # schema `meta` (defaut pour ce modele).
    # / Create a minimal draft (required fields only) in the `meta` schema
    # (default for this model).
    wc = WaitingConfiguration.objects.create(
        organisation="OnboardTestViewsetOrg",
        email="onboard-test-viewset@example.com",
        dns_choice="tibillet.localhost",
        phone="0102030405",
    )
    cleanup_waiting_configs(wc)

    request = _make_request_with_session()

    # 1) Session vide -> None. / Empty session -> None.
    assert _get_or_none_wc(request) is None

    # 2) Apres _set, on retrouve la meme instance via _get.
    # / After _set, _get returns the same instance.
    _set_session_wc(request, wc)
    assert request.session.get(SESSION_KEY) == str(wc.uuid)
    fetched = _get_or_none_wc(request)
    assert fetched is not None
    assert fetched.uuid == wc.uuid

    # 3) Apres _clear, on revient a None. / After _clear, back to None.
    _clear_session_wc(request)
    assert SESSION_KEY not in request.session
    assert _get_or_none_wc(request) is None


def test_onboard_root_redirects_to_identity_when_no_session_wc():
    """
    GET sur la vue racine sans brouillon en session : 302 vers
    `/onboard/identity/`. Test direct via le ViewSet (pas le client HTTP) :
    on n'a pas besoin de monter un tenant ni de gerer l'hote dans ce
    test unitaire.
    / GET on the root view without a draft: 302 to `/onboard/identity/`.
    Tested directly via the ViewSet (not the HTTP client): no need to
    set up a tenant or host in this unit test.
    """
    request = _make_request_with_session()

    # Binde la vue comme le fait le routeur Django et appelle.
    # / Bind the view as Django's router does, then call.
    view = OnboardViewSet.as_view({"get": "root"})
    response = view(request)

    # Apres refactor Task 10 : redirect vers la step identity.
    # / After Task 10 refactor: redirect to identity step.
    assert response.status_code in (302, 303)
    assert response["Location"] == "/onboard/identity/"
