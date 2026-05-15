"""
Tests de la step 3 — Place (Task 12).
/ Tests for wizard step 3 — Place (Task 12).

LOCALISATION: onboard/tests/test_step_place.py

On verifie :
  1. POST `/onboard/place/` avec donnees valides -> redirige (302/303)
     vers `/onboard/descriptions/`, le brouillon est mis a jour :
       - street_address / postal_code / address_locality / address_country
       - latitude / longitude
       - current_step="descriptions".
  2. POST `/onboard/place/` avec donnees invalides (lat hors range) -> 422
     + le HTML contient un message d'erreur.

NOTE : `short_description` n'est plus dans le payload de cette step
(feedback mainteneur 2026-05-14, deplace vers la step "Presentation").
Le serializer rejetterait silencieusement la cle (Serializer ignore les
champs non declares), mais on la retire pour rester explicite.

/ We verify:
  1. POST `/onboard/place/` with valid data -> 302/303 to
     `/onboard/descriptions/`, draft updated (address fields + GPS +
     current_step).
  2. POST `/onboard/place/` with invalid data (lat out of range) -> 422.

NOTE: `short_description` is no longer part of this step's payload
(moved to the "Presentation" step).

PIEGE : `WaitingConfiguration` vit dans le schema `meta` (cf. tests des
steps precedentes). On force `schema_context("meta")` avant chaque acces
ORM. / PITFALL: `WaitingConfiguration` lives in the `meta` schema. Force
`schema_context("meta")` before any ORM access.
"""

import time

import pytest
from django.test import Client
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


# Tous les tests de ce module sont marques `onboard` (cf. pytest.ini).
# / All tests here are marked `onboard` (cf. pytest.ini).
pytestmark = pytest.mark.onboard


# Hote HTTP de dev par defaut (cf. pattern V2 du projet).
# / Default dev HTTP host (V2 project pattern).
DEV_HOST = "lespass.tibillet.localhost"


# ---------------------------------------------------------------------------
# Helpers locaux. / Local helpers.
# ---------------------------------------------------------------------------


def test_place_get_kicks_out_unauthenticated_user_to_identity(cleanup_waiting_configs):
    """
    Regression : si l'utilisateur a un brouillon `email_confirmed=True`
    en session MAIS n'est PAS Django-authenticated (cas : logout silencieux,
    cookie expire, etc.), GET `/onboard/place/` redirige vers
    `/onboard/identity/`. Defense en profondeur du
    `_get_confirmed_wc_or_redirect` (refacto 2026-05-15).

    Sans le check `is_authenticated`, un attaquant qui pourrait restaurer
    la session WC d'un autre user (cookie hijack) accederait aux steps
    sans avoir prouve l'email. Le double check (WC + auth) durcit le flow.

    / Regression: a draft `email_confirmed=True` in session WITHOUT a
    Django-authenticated user (silent logout, expired cookie) must still
    redirect to identity. Defense in depth.
    """
    import time

    client = Client(HTTP_HOST=DEV_HOST)

    # Cree un WC confirme + pose la session SANS faire de login.
    # / Create a confirmed WC + set session WITHOUT login.
    unique_email = f"kickout-{int(time.time() * 1000000)}@example.com"
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Kickout Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_PLACE,
            phone="",
        )
    cleanup_waiting_configs(wc)

    session = client.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    # Pas de force_login -> user reste anonymous.

    response = client.get("/onboard/place/")

    assert response.status_code in (302, 303), (
        f"Expected redirect, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/identity/", (
        f"Expected redirect to /onboard/identity/, got {response['Location']!r}. "
        f"Sans auth, le user doit etre kick out vers identity."
    )


def _create_wc_at_place(client, cleanup=None):
    """
    Cree un WaitingConfiguration en schema `meta` deja pre-positionne sur
    `current_step="place"` avec `email_confirmed=True` (la step 3 exige
    que l'OTP ait deja ete valide), et fixe la session Django du `client`
    de test sur ce WC.

    / Create a WaitingConfiguration in the `meta` schema already at
    `current_step="place"` with `email_confirmed=True` (step 3 requires
    a verified email), and pin the test client's session to this WC.

    :param client: instance `django.test.Client`.
    :param cleanup: fixture `cleanup_waiting_configs` (callable optional).
    :return: instance WaitingConfiguration creee.
    """
    # Suffixe unique pour eviter les collisions avec d'anciens WC en DB dev.
    # / Unique suffix to avoid collisions with stale dev DB rows.
    unique_email = f"place-{int(time.time() * 1000000)}@example.com"

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Place Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_PLACE,
            phone="",
        )
    if cleanup is not None:
        cleanup(wc)

    # Fixe l'UUID dans la session du client de test. `Client.session` est
    # une propriete : copier dans une variable locale, modifier, puis
    # sauvegarder explicitement.
    # / Pin UUID in the test client's session. `Client.session` is a
    # property: copy to a local, mutate, then save explicitly.
    session = client.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()

    # Login Django : depuis 2026-05-15 les steps post-verify exigent
    # `is_authenticated` (cf. _get_confirmed_wc_or_redirect dans views.py).
    # / Django login: post-verify steps require `is_authenticated`.
    from onboard.tests.helpers import login_test_user_for_email
    login_test_user_for_email(client, unique_email)

    return wc


# ---------------------------------------------------------------------------
# Tests. / Tests.
# ---------------------------------------------------------------------------


def test_place_post_saves_address_and_advances_to_descriptions(cleanup_waiting_configs):
    """
    POST `/onboard/place/` avec donnees valides :
      - retourne 302/303 vers `/onboard/descriptions/`,
      - persiste l'adresse + GPS dans le brouillon,
      - avance `current_step` vers "descriptions".

    `short_description` n'est plus accepte sur cette step (deplace vers
    "Presentation"). On verifie que la step Place ne touche pas a ce champ.

    / POST `/onboard/place/` with valid data:
      - returns 302/303 to `/onboard/descriptions/`,
      - persists address + GPS on the draft,
      - moves `current_step` to "descriptions".

    `short_description` is no longer accepted on this step (moved to
    "Presentation"). We assert the Place step does NOT touch that field.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at_place(client, cleanup=cleanup_waiting_configs)

    response = client.post("/onboard/place/", data={
        "street_address": "1 rue Test",
        "postal_code": "97400",
        "address_locality": "St Denis",
        "address_country": "Réunion",
        "place_latitude": "-20.88",
        "place_longitude": "55.45",
        "place_adresse": "1 rue Test, 97400 St Denis, Réunion",
    })

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/descriptions/"

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_DESCRIPTIONS
    assert wc.street_address == "1 rue Test"
    assert wc.postal_code == "97400"
    assert wc.address_locality == "St Denis"
    assert wc.address_country == "Réunion"
    # short_description doit rester vide : la step Place n'y touche plus.
    # / short_description must stay empty: the Place step no longer writes it.
    assert not wc.short_description, (
        f"short_description should be untouched by step Place, "
        f"got {wc.short_description!r}"
    )
    assert float(wc.latitude) == pytest.approx(-20.88, rel=1e-3)
    assert float(wc.longitude) == pytest.approx(55.45, rel=1e-3)


def test_place_post_invalid_data_returns_422(cleanup_waiting_configs):
    """
    POST `/onboard/place/` avec une latitude hors plage (-200) -> 422.
    Le brouillon ne doit pas etre avance (current_step reste "place").

    / POST `/onboard/place/` with out-of-range latitude (-200) -> 422.
    Draft must not advance (current_step stays "place").
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at_place(client, cleanup=cleanup_waiting_configs)

    response = client.post("/onboard/place/", data={
        "street_address": "1 rue Test",
        "postal_code": "97400",
        "address_locality": "St Denis",
        "address_country": "Réunion",
        "place_latitude": "-200",  # hors plage [-90, 90] / out of range
        "place_longitude": "55.45",
    })

    assert response.status_code == 422, (
        f"Expected 422, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Le brouillon doit etre intact. / Draft must be unchanged.
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_PLACE
