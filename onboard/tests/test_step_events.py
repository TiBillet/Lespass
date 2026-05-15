"""
Tests de la step 5 — Events (add/remove sous-form HTMX + finalize) (Task 14).
/ Tests for wizard step 5 — Events (add/remove HTMX sub-form + finalize) (Task 14).

LOCALISATION: onboard/tests/test_step_events.py

On verifie :
  1. POST `/onboard/events/add/` avec donnees valides ->
     `wc.events_draft` contient un nouvel event avec le bon `name`.
  2. POST `/onboard/events/<idx>/remove/` -> retire l'event a l'index
     demande de `wc.events_draft`.
  3. POST `/onboard/events/` (finalisation) -> redirige vers
     `/onboard/launch/`, `wc.current_step="launch"` et la task
     `create_tenant_from_draft.delay` est appelee avec `wc_uuid=str(wc.uuid)`.

/ We verify:
  1. POST `/onboard/events/add/` with valid data -> `wc.events_draft`
     contains a new event with the expected `name`.
  2. POST `/onboard/events/<idx>/remove/` -> removes the event at the
     given index from `wc.events_draft`.
  3. POST `/onboard/events/` (finalize) -> redirects to `/onboard/launch/`,
     `wc.current_step="launch"`, and `create_tenant_from_draft.delay` is
     called with `wc_uuid=str(wc.uuid)`.

PIEGE : `WaitingConfiguration` vit dans le schema `meta` (cf. tests des
steps precedentes). On force `schema_context("meta")` avant chaque acces
ORM. / PITFALL: `WaitingConfiguration` lives in the `meta` schema. Force
`schema_context("meta")` before any ORM access.

PIEGE : patcher `onboard.tasks.create_tenant_from_draft.delay` directement
fonctionne car la vue fait un import local (`from onboard.tasks import
create_tenant_from_draft`) puis appelle `.delay()` sur l'objet
re-importe : le mock pose sur l'attribut `delay` du shared_task est
visible. / PITFALL: patching `onboard.tasks.create_tenant_from_draft.delay`
works because the view does a local import then calls `.delay()` on the
re-imported object — the mock on the `delay` attribute of the shared_task
is observed.
"""

import io
import time
from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
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


def _make_wc_at_events(client, cleanup=None):
    """
    Cree un WaitingConfiguration en schema `meta` deja pre-positionne sur
    `current_step="events"` avec `email_confirmed=True` (la step 5 exige
    que l'OTP ait deja ete valide), et fixe la session Django du `client`
    de test sur ce WC.

    / Create a WaitingConfiguration in the `meta` schema already at
    `current_step="events"` with `email_confirmed=True`, and pin the test
    client's session to this WC.

    :param client: instance `django.test.Client`.
    :param cleanup: fixture `cleanup_waiting_configs` (callable optional).
    :return: instance WaitingConfiguration creee.
    """
    # Suffixe unique pour eviter les collisions avec d'anciens WC en DB dev.
    # / Unique suffix to avoid collisions with stale dev DB rows.
    unique_email = f"events-{int(time.time() * 1000000)}@example.com"

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Events Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_EVENTS,
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


def _make_test_image_bytes(name="event.png"):
    """
    Genere un PNG 10x10 en memoire pour servir d'image d'event de test.
    Renvoie un `SimpleUploadedFile` pret a etre envoye via `client.post`.

    / Generate a 10x10 in-memory PNG to use as a test event image.
    Returns a `SimpleUploadedFile` ready for `client.post`.
    """
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(
        name=name,
        content=buffer.read(),
        content_type="image/png",
    )


# ---------------------------------------------------------------------------
# Tests. / Tests.
# ---------------------------------------------------------------------------


def test_events_add_appends_to_jsonfield(cleanup_waiting_configs):
    """
    POST `/onboard/events/add/` avec donnees valides :
      - retourne 200 (HTMX partial),
      - persiste un event dans `wc.events_draft[0]` avec le bon `name`.

    / POST `/onboard/events/add/` with valid data:
      - returns 200 (HTMX partial),
      - persists an event in `wc.events_draft[0]` with the right `name`.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_events(client, cleanup=cleanup_waiting_configs)

    response = client.post(
        "/onboard/events/add/",
        data={
            "name": "Concert d'ouverture",
            # Format datetime-local ISO 8601 sans timezone (acceptable par
            # DRF DateTimeField, qui le parse en datetime naive).
            # / ISO 8601 datetime-local format without timezone (parsed by
            # DRF DateTimeField as a naive datetime).
            "datetime": "2026-06-15T20:00",
            "description": "Premier evenement du lieu.",
        },
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )

    # Reload du brouillon pour verifier la persistance.
    # / Reload the draft to verify persistence.
    with schema_context("meta"):
        wc.refresh_from_db()
    assert isinstance(wc.events_draft, list), (
        f"events_draft should be a list, got {type(wc.events_draft)!r}"
    )
    assert len(wc.events_draft) == 1, (
        f"Expected 1 event, got {len(wc.events_draft)}: {wc.events_draft!r}"
    )
    assert wc.events_draft[0]["name"] == "Concert d'ouverture"
    # `datetime` est stocke en ISO 8601 (string) — pas comme datetime object.
    # / `datetime` is stored as ISO 8601 string, not a datetime object.
    assert isinstance(wc.events_draft[0]["datetime"], str)


def test_events_remove_by_index(cleanup_waiting_configs):
    """
    POST `/onboard/events/0/remove/` :
      - retourne 200 (HTMX partial),
      - retire le 1er event de `wc.events_draft`,
      - la liste contient uniquement le 2eme event.

    / POST `/onboard/events/0/remove/`:
      - returns 200 (HTMX partial),
      - removes the 1st event from `wc.events_draft`,
      - the list now contains only the 2nd event.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_events(client, cleanup=cleanup_waiting_configs)

    # Pre-remplit la liste avec deux events via save() direct (on n'utilise
    # pas l'endpoint add ici : on isole le test de remove).
    # / Pre-fill list with two events via direct .save() (isolate remove test).
    with schema_context("meta"):
        wc.events_draft = [
            {"name": "A", "datetime": "2026-06-15T20:00:00", "description": ""},
            {"name": "B", "datetime": "2026-07-01T19:00:00", "description": ""},
        ]
        wc.save(update_fields=["events_draft"])

    response = client.post("/onboard/events/0/remove/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )

    with schema_context("meta"):
        wc.refresh_from_db()
    assert len(wc.events_draft) == 1, (
        f"Expected 1 event left, got {len(wc.events_draft)}: {wc.events_draft!r}"
    )
    assert wc.events_draft[0]["name"] == "B"


def test_events_add_with_image_persists_path_and_file(cleanup_waiting_configs):
    """
    POST `/onboard/events/add/` avec une image valide :
      - retourne 200 (HTMX partial),
      - persiste `wc.events_draft[0]["image"]` avec un path relatif,
      - le fichier existe vraiment sur disque via `default_storage`.

    Cleanup file via `default_storage.delete` pour ne pas polluer
    `MEDIA_ROOT` entre les runs.

    / POST `/onboard/events/add/` with a valid image:
      - returns 200 (HTMX partial),
      - persists `wc.events_draft[0]["image"]` with a relative path,
      - file actually exists on disk via `default_storage`.

    Cleanup file with `default_storage.delete` to avoid polluting
    `MEDIA_ROOT` across runs.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_events(client, cleanup=cleanup_waiting_configs)

    response = client.post(
        "/onboard/events/add/",
        data={
            "name": "Concert avec image",
            "datetime": "2026-06-15T20:00",
            "description": "Avec affiche.",
            "image": _make_test_image_bytes(),
        },
        format="multipart",
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )

    with schema_context("meta"):
        wc.refresh_from_db()
    assert len(wc.events_draft) == 1
    event = wc.events_draft[0]
    assert "image" in event, f"Image key missing in {event!r}"
    image_path = event["image"]
    # Path attendu : `onboard_drafts/<wc_uuid>/events/<uuid>.png`.
    # / Expected path: `onboard_drafts/<wc_uuid>/events/<uuid>.png`.
    assert image_path.startswith(f"onboard_drafts/{wc.uuid}/events/"), (
        f"Unexpected image path layout: {image_path!r}"
    )
    assert image_path.endswith(".png"), (
        f"Expected .png extension, got {image_path!r}"
    )

    # Le fichier doit reellement exister sur disque.
    # / The file must actually exist on disk.
    assert default_storage.exists(image_path), (
        f"File should exist on disk at {image_path!r}"
    )

    # Cleanup explicite du fichier pour ne pas polluer le MEDIA_ROOT dev.
    # / Explicit cleanup to keep dev MEDIA_ROOT clean.
    default_storage.delete(image_path)


def test_events_remove_with_image_deletes_file(cleanup_waiting_configs):
    """
    POST `/onboard/events/0/remove/` quand l'event a une image :
      - retourne 200,
      - retire l'event du JSON,
      - supprime aussi le fichier image sur disque via `default_storage`.

    / POST `/onboard/events/0/remove/` when event has an image:
      - returns 200,
      - removes event from JSON,
      - also deletes the image file on disk via `default_storage`.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_events(client, cleanup=cleanup_waiting_configs)

    # On ajoute un event via l'endpoint pour avoir un vrai fichier sur disque.
    # / Add an event via the endpoint so a real file lands on disk.
    add_response = client.post(
        "/onboard/events/add/",
        data={
            "name": "A supprimer",
            "datetime": "2026-06-15T20:00",
            "description": "",
            "image": _make_test_image_bytes(),
        },
        format="multipart",
    )
    assert add_response.status_code == 200

    with schema_context("meta"):
        wc.refresh_from_db()
    image_path = wc.events_draft[0]["image"]
    assert default_storage.exists(image_path), "Setup: file should exist"

    # Remove de l'event. / Remove the event.
    remove_response = client.post("/onboard/events/0/remove/")
    assert remove_response.status_code == 200

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.events_draft == [], (
        f"Events list should be empty after remove, got {wc.events_draft!r}"
    )
    # Le fichier doit avoir ete supprime.
    # / The file must have been deleted.
    assert not default_storage.exists(image_path), (
        f"File should have been deleted: {image_path!r}"
    )


def test_events_finalize_advances_to_launch_and_enqueues_task(cleanup_waiting_configs):
    """
    POST `/onboard/events/` (finalisation) :
      - redirige vers `/onboard/launch/`,
      - avance `wc.current_step` a "launch",
      - appelle `create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))`.

    On patche `onboard.tasks.create_tenant_from_draft.delay` pour ne PAS
    enqueuer reellement dans Celery (sinon le worker tenterait de creer
    un vrai tenant en DB dev).

    / POST `/onboard/events/` (finalize):
      - redirects to `/onboard/launch/`,
      - advances `wc.current_step` to "launch",
      - calls `create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))`.

    We patch `onboard.tasks.create_tenant_from_draft.delay` so the task
    isn't actually enqueued (otherwise the Celery worker would try to
    create a real tenant in the dev DB).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_events(client, cleanup=cleanup_waiting_configs)

    with patch("onboard.tasks.create_tenant_from_draft.delay") as mock_delay:
        response = client.post("/onboard/events/", data={})

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/launch/"

    # Le brouillon doit etre passe a "launch".
    # / The draft must have advanced to "launch".
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.current_step == WaitingConfiguration.STEP_LAUNCH

    # La task doit avoir ete enqueuee une fois avec le bon UUID en string.
    # / The task must have been enqueued once with the right UUID as string.
    mock_delay.assert_called_once_with(wc_uuid=str(wc.uuid))
