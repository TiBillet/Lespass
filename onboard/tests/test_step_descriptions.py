"""
Tests de la step 4 — Descriptions + logo upload (Task 13).
/ Tests for wizard step 4 — Descriptions + logo upload (Task 13).

LOCALISATION: onboard/tests/test_step_descriptions.py

On verifie :
  1. POST `/onboard/descriptions/` avec `short_description` +
     `long_description` + `logo` valide -> 302/303 vers `/onboard/events/`,
     le brouillon est mis a jour :
       - short_description rempli,
       - long_description rempli,
       - logo non vide (fichier persiste sur disque),
       - current_step="events".
  2. POST avec `short_description` seul (long_description et logo
     optionnels) -> 302/303 + short_description rempli, long_description
     vide, logo vide. Verifie que le serializer accepte l'absence de
     long_description et de logo.
  3. POST avec `long_description` > 5000 chars -> 422 (short_description
     valide).

NOTE : `short_description` est sur cette step depuis 2026-05-14 (feedback
mainteneur : regrouper toutes les descriptions sur une meme page).
`long_description` et `logo` sont optionnels.

/ We verify:
  1. POST with `short_description` + `long_description` + valid `logo`
     -> 302/303 to `/onboard/events/`, draft updated (short desc + long
     desc + logo + current_step).
  2. POST with `short_description` only (long_description and logo
     optional) -> 302/303 + short desc filled, long desc empty, logo
     empty.
  3. POST with `long_description` > 5000 chars -> 422 (short_description
     is valid).

NOTE: `short_description` lives on this step since 2026-05-14 (maintainer
feedback: group all descriptions onto a single page). `long_description`
and `logo` are optional.

PIEGE : `WaitingConfiguration` vit dans le schema `meta` (cf. tests des
steps precedentes). On force `schema_context("meta")` avant chaque acces
ORM. / PITFALL: `WaitingConfiguration` lives in the `meta` schema. Force
`schema_context("meta")` before any ORM access.

PIEGE : upload de fichier en test = `format="multipart"` sur `client.post`.
Le fichier uploade est persiste dans `MEDIA_ROOT/images/` (vrai disque).
Le cleanup_waiting_configs supprime le WC mais PAS le fichier media —
acceptable en dev DB, ce sont des orphelins que `purge_stale_onboard_drafts`
nettoiera en follow-up.
/ PITFALL: file upload in tests = `format="multipart"` on `client.post`.
The uploaded file lands in `MEDIA_ROOT/images/` (real disk). The cleanup
fixture removes the WC but NOT the media file — these orphans are
expected to be reaped by `purge_stale_onboard_drafts`.
"""

import io
import time

import pytest
from django.test import Client
from django_tenants.utils import schema_context
from PIL import Image

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


def _create_wc_at_descriptions(client, cleanup=None):
    """
    Cree un WaitingConfiguration en schema `meta` deja pre-positionne sur
    `current_step="descriptions"` avec `email_confirmed=True` (la step 4
    exige que l'OTP ait deja ete valide), et fixe la session Django du
    `client` de test sur ce WC.

    / Create a WaitingConfiguration in the `meta` schema already at
    `current_step="descriptions"` with `email_confirmed=True`, and pin
    the test client's session to this WC.

    :param client: instance `django.test.Client`.
    :param cleanup: fixture `cleanup_waiting_configs` (callable optional).
    :return: instance WaitingConfiguration creee.
    """
    # Suffixe unique pour eviter les collisions avec d'anciens WC en DB dev.
    # / Unique suffix to avoid collisions with stale dev DB rows.
    unique_email = f"descriptions-{int(time.time() * 1000000)}@example.com"

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Descriptions Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_DESCRIPTIONS,
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


def _make_test_image_bytes():
    """
    Genere un PNG 10x10 en memoire pour servir de logo de test.
    Renvoie un `SimpleUploadedFile` pret a etre envoye via `client.post`.

    / Generates a 10x10 in-memory PNG for use as a test logo.
    Returns a `SimpleUploadedFile` ready to be sent via `client.post`.
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(
        name="test-logo.png",
        content=buffer.read(),
        content_type="image/png",
    )


# ---------------------------------------------------------------------------
# Tests. / Tests.
# ---------------------------------------------------------------------------


def test_descriptions_post_saves_long_desc_and_logo(cleanup_waiting_configs):
    """
    POST `/onboard/descriptions/` avec donnees valides + logo :
      - retourne 302/303 vers `/onboard/events/`,
      - persiste `short_description` dans le brouillon,
      - persiste `long_description` dans le brouillon,
      - persiste `logo` (fichier non vide),
      - avance `current_step` vers "events".

    / POST `/onboard/descriptions/` with valid data + logo:
      - returns 302/303 to `/onboard/events/`,
      - persists `short_description` on the draft,
      - persists `long_description` on the draft,
      - persists `logo` (non-empty file),
      - moves `current_step` to "events".
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at_descriptions(client, cleanup=cleanup_waiting_configs)

    short_desc = "Un lieu de test pour l'accroche publique."
    long_desc = "Voici une description longue de notre lieu accueillant."
    response = client.post(
        "/onboard/descriptions/",
        data={
            "short_description": short_desc,
            "long_description": long_desc,
            "logo": _make_test_image_bytes(),
        },
        format="multipart",
    )

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/events/"

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_EVENTS
    assert wc.short_description == short_desc
    assert wc.long_description == long_desc
    # Le logo doit etre persiste : FieldFile non vide + nom de fichier set.
    # / Logo must be persisted: non-empty FieldFile with a filename.
    assert wc.logo, f"Logo should be set, got {wc.logo!r}"
    assert wc.logo.name, f"Logo should have a name, got {wc.logo.name!r}"


def test_descriptions_post_without_logo_is_ok(cleanup_waiting_configs):
    """
    POST `/onboard/descriptions/` avec seulement `short_description`
    (long_description et logo sont optionnels) :
      - retourne 302/303 vers `/onboard/events/`,
      - persiste `short_description`,
      - `wc.long_description` reste vide,
      - `wc.logo` reste vide,
      - avance `current_step` vers "events".

    Verifie que le serializer accepte bien l'absence de logo
    (`required=False, allow_null=True`) ET l'absence de long_description
    (`required=False, allow_blank=True`).

    / POST with only `short_description` (long_description and logo are
    optional):
      - returns 302/303 to `/onboard/events/`,
      - persists `short_description`,
      - `wc.long_description` stays empty,
      - `wc.logo` stays empty,
      - moves `current_step` to "events".

    Checks the serializer accepts a missing logo AND a missing
    long_description.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at_descriptions(client, cleanup=cleanup_waiting_configs)

    short_desc = "Accroche minimale, juste ce qu'il faut."
    response = client.post(
        "/onboard/descriptions/",
        data={"short_description": short_desc},
        format="multipart",
    )

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/events/"

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_EVENTS
    assert wc.short_description == short_desc
    # `wc.long_description` doit etre vide (champ optionnel non envoye).
    # / `wc.long_description` must be empty (optional field, not sent).
    assert not wc.long_description, (
        f"long_description should be empty, got {wc.long_description!r}"
    )
    # `wc.logo` doit etre vide (FieldFile falsy quand pas de fichier).
    # / `wc.logo` must be empty (FieldFile is falsy when no file).
    assert not wc.logo, f"Logo should be empty, got {wc.logo!r}"


def test_descriptions_post_too_long_returns_422(cleanup_waiting_configs):
    """
    POST `/onboard/descriptions/` avec `long_description` > 5000 chars -> 422.
    Le brouillon ne doit pas etre avance (current_step reste "descriptions").

    On envoie un `short_description` valide pour isoler l'erreur sur
    `long_description` (sans short_description, on aurait aussi une
    erreur de champ requis qui parasiterait l'assertion).

    / POST with `long_description` > 5000 chars -> 422.
    Draft must not advance (current_step stays "descriptions").

    A valid `short_description` is supplied so the only validation error
    comes from the oversized long description.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_at_descriptions(client, cleanup=cleanup_waiting_configs)

    # 5001 caracteres : juste au-dessus de la limite serializer (5000).
    # / 5001 chars: just above the serializer limit (5000).
    too_long = "a" * 5001
    response = client.post(
        "/onboard/descriptions/",
        data={
            "short_description": "Accroche valide",
            "long_description": too_long,
        },
        format="multipart",
    )

    assert response.status_code == 422, (
        f"Expected 422, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Le brouillon doit etre intact. / Draft must be unchanged.
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_DESCRIPTIONS
