"""
Tests de la step 3 — Place + endpoint geocode (Task 12).
/ Tests for wizard step 3 — Place + geocode endpoint (Task 12).

LOCALISATION: onboard/tests/test_step_place.py

On verifie :
  1. POST `/onboard/place/` avec donnees valides -> redirige (302/303)
     vers `/onboard/descriptions/`, le brouillon est mis a jour :
       - street_address / postal_code / address_locality / address_country
       - latitude / longitude
       - current_step="descriptions".
  2. POST `/onboard/geocode/` (sans appel reseau reel) -> 200 + partial HTML
     contenant la latitude resolvee. La fonction `geocode` est patchee
     pour ne pas frapper Nominatim depuis les tests.
  3. POST `/onboard/place/` avec donnees invalides (lat hors range) -> 422
     + le HTML contient un message d'erreur.

NOTE : `short_description` n'est plus dans le payload de cette step
(feedback mainteneur 2026-05-14, deplace vers la step "Presentation").
Le serializer rejetterait silencieusement la cle (Serializer ignore les
champs non declares), mais on la retire pour rester explicite.

/ We verify:
  1. POST `/onboard/place/` with valid data -> 302/303 to
     `/onboard/descriptions/`, draft updated (address fields + GPS +
     current_step).
  2. POST `/onboard/geocode/` (no real network call) -> 200 + partial HTML
     with the resolved latitude. `geocode` is patched.
  3. POST `/onboard/place/` with invalid data (lat out of range) -> 422.

NOTE: `short_description` is no longer part of this step's payload
(moved to the "Presentation" step).

PIEGE : `WaitingConfiguration` vit dans le schema `meta` (cf. tests des
steps precedentes). On force `schema_context("meta")` avant chaque acces
ORM. / PITFALL: `WaitingConfiguration` lives in the `meta` schema. Force
`schema_context("meta")` before any ORM access.

PIEGE : `onboard.views.geocode` est importe au top du module pour que
le patch fonctionne. On patche bien `onboard.views.geocode` (et non
`onboard.services.geocode`) car la vue resout le nom depuis son propre
module. / PITFALL: `onboard.views.geocode` is imported at module-top so
the patch works. We patch `onboard.views.geocode` (not
`onboard.services.geocode`) because the view resolves the name from its
own module.
"""

import time
from unittest.mock import patch

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
        "latitude": "-20.88",
        "longitude": "55.45",
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


def test_geocode_endpoint_returns_partial_with_coords(cleanup_waiting_configs):
    """
    POST `/onboard/geocode/` avec une query, en patchant `geocode` pour
    eviter tout appel reseau reel. La reponse doit etre 200 + un partial
    HTML contenant la latitude resolue.

    On a besoin d'un brouillon en session car l'endpoint est sous la
    meme ViewSet — meme si la vue elle-meme ne lit pas wc, on aligne
    le contexte sur celui d'un user au step 3.

    / POST `/onboard/geocode/` with a query, patching `geocode` to avoid
    real network calls. Response should be 200 + HTML partial with the
    resolved latitude.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    _create_wc_at_place(client, cleanup=cleanup_waiting_configs)

    fake_result = {"latitude": 48.85, "longitude": 2.35, "display_name": "Paris"}
    with patch("onboard.views.geocode", return_value=fake_result):
        response = client.post("/onboard/geocode/", data={"query": "Paris"})

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert b"48.85" in response.content


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
        "latitude": "-200",  # hors plage [-90, 90] / out of range
        "longitude": "55.45",
    })

    assert response.status_code == 422, (
        f"Expected 422, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Le brouillon doit etre intact. / Draft must be unchanged.
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_PLACE
