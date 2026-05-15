"""
Tests de la step 6 — Launch + status polling + retry + resume (Task 15).
/ Tests for wizard step 6 — Launch + status polling + retry + resume (Task 15).

LOCALISATION: onboard/tests/test_step_launch.py

On verifie :
  1. GET `/onboard/launch/` rend la page (200) avec mention du carrousel.
  2. GET `/onboard/launch/status/` sans tenant attache -> partial
     `status_progress.html` contenant `every 2s` (polling continue).
  3. GET `/onboard/launch/status/` avec `wc.tenant` defini -> partial
     `status_done.html` sans `every 2s` + domaine dans le HTML.
  4. GET `/onboard/launch/status/` avec `wc.error_message` non vide ->
     partial `status_error.html` contenant le message d'erreur.
  5. GET `/onboard/resume/<signed>/` valide -> 302 vers la step courante.
  6. GET `/onboard/resume/<bad>/` invalide -> 400 + partial invalid.

/ We verify:
  1. GET `/onboard/launch/` renders (200) with carousel mention.
  2. GET `/onboard/launch/status/` without tenant attached -> partial
     `status_progress.html` containing `every 2s` (polling continues).
  3. GET `/onboard/launch/status/` with `wc.tenant` set -> partial
     `status_done.html` without `every 2s` + domain in HTML.
  4. GET `/onboard/launch/status/` with non-empty `wc.error_message` ->
     partial `status_error.html` containing the error message.
  5. GET `/onboard/resume/<signed>/` valid -> 302 to current step.
  6. GET `/onboard/resume/<bad>/` invalid -> 400 + invalid partial.

PIEGE : `WaitingConfiguration` vit dans le schema `meta` (cf. autres tests
de steps). On force `schema_context("meta")` avant chaque acces ORM.
/ PITFALL: `WaitingConfiguration` lives in the `meta` schema. Force
`schema_context("meta")` before any ORM access.

PIEGE : la fixture `lespass_tenant` reutilise le tenant deja present en
DB dev (pas de `auto_create_schema=True` lent). On l'attache au WC via
`tenant=lespass_tenant` pour simuler "tenant cree" sans creer un vrai
schema. / PITFALL: the `lespass_tenant` fixture reuses the existing dev
DB tenant (no slow `auto_create_schema=True`). We attach it to the WC
via `tenant=lespass_tenant` to simulate "tenant created" without
creating a real schema.
"""

import time
from unittest.mock import patch

import pytest
from django.core import signing
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


def _make_wc_at_launch(client, cleanup=None, tenant=None, error_message=""):
    """
    Cree un WaitingConfiguration en schema `meta` pre-positionne sur
    `current_step="launch"` avec `email_confirmed=True`, et fixe la
    session Django du `client` de test sur ce WC.

    / Create a WaitingConfiguration in the `meta` schema already at
    `current_step="launch"` with `email_confirmed=True`, and pin the test
    client's session to this WC.

    :param client: instance `django.test.Client`.
    :param cleanup: fixture `cleanup_waiting_configs` (callable optional).
    :param tenant: instance `Client` a attacher au WC (None par defaut).
    :param error_message: message d'erreur pre-rempli (vide par defaut).
    :return: instance WaitingConfiguration creee.
    """
    # Suffixe unique pour eviter les collisions avec d'anciens WC en DB dev.
    # / Unique suffix to avoid collisions with stale dev DB rows.
    unique_email = f"launch-{int(time.time() * 1000000)}@example.com"

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Launch Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_LAUNCH,
            phone="",
            tenant=tenant,
            error_message=error_message,
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


def test_launch_get_renders_page_with_carousel(cleanup_waiting_configs):
    """
    GET `/onboard/launch/` :
      - retourne 200,
      - contient le mot "carrousel" (Task 19 finalisera le contenu).

    / GET `/onboard/launch/`:
      - returns 200,
      - contains the word "carrousel" (Task 19 will finalize content).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    _make_wc_at_launch(client, cleanup=cleanup_waiting_configs)

    response = client.get("/onboard/launch/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Le mot doit apparaitre quelque part dans la page : recap, mention
    # textuelle, ou heading. On accepte les deux orthographes possibles.
    # / The word must appear somewhere in the page: recap, textual
    # mention, or heading. Accept both spellings.
    body_lower = response.content.lower()
    assert b"carrousel" in body_lower or b"carousel" in body_lower, (
        "Expected 'carrousel' or 'carousel' in /onboard/launch/ response."
    )


def test_status_endpoint_progress_when_no_tenant(cleanup_waiting_configs):
    """
    GET `/onboard/launch/status/` sans tenant attache :
      - retourne 200,
      - le partial `status_progress.html` contient `every 2s` (polling
        HTMX continue automatiquement).

    / GET `/onboard/launch/status/` without tenant attached:
      - returns 200,
      - the `status_progress.html` partial contains `every 2s` (HTMX
        polling continues automatically).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    _make_wc_at_launch(client, cleanup=cleanup_waiting_configs)

    response = client.get("/onboard/launch/status/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Polling actif : `hx-trigger="every 2s"` doit etre present.
    # / Active polling: `hx-trigger="every 2s"` must be present.
    assert b"every 2s" in response.content, (
        "Expected `every 2s` in progress partial to keep polling. "
        f"Body excerpt: {response.content[:300]!r}"
    )


def test_status_endpoint_done_when_tenant_set(
    cleanup_waiting_configs, lespass_tenant,
):
    """
    GET `/onboard/launch/status/` avec `wc.tenant=lespass_tenant` :
      - retourne 200,
      - PAS de `every 2s` (polling doit s'arreter),
      - le domaine primaire du tenant `lespass` apparait dans le HTML.

    / GET `/onboard/launch/status/` with `wc.tenant=lespass_tenant`:
      - returns 200,
      - NO `every 2s` (polling must stop),
      - the primary domain of `lespass` tenant appears in the HTML.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    _make_wc_at_launch(
        client, cleanup=cleanup_waiting_configs, tenant=lespass_tenant,
    )

    response = client.get("/onboard/launch/status/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Polling doit etre arrete (template `status_done.html` ne porte pas
    # `every 2s`). / Polling must be stopped (`status_done.html` has no
    # `every 2s`).
    assert b"every 2s" not in response.content, (
        "Expected NO `every 2s` in done partial (polling must stop). "
        f"Body excerpt: {response.content[:300]!r}"
    )

    # Domaine primaire visible dans le HTML.
    # / Primary domain visible in HTML.
    primary = lespass_tenant.get_primary_domain()
    assert primary is not None, (
        "Fixture `lespass_tenant` doit avoir un primary domain."
    )
    expected_domain = primary.domain.encode("utf-8")
    assert expected_domain in response.content, (
        f"Expected domain {primary.domain!r} in done partial. "
        f"Body excerpt: {response.content[:500]!r}"
    )


def test_status_endpoint_error_when_error_message(cleanup_waiting_configs):
    """
    GET `/onboard/launch/status/` avec `wc.error_message="Pool epuise"` :
      - retourne 200,
      - le message d'erreur apparait dans le partial,
      - le partial est bien le partial d'erreur (mention du retry).

    / GET `/onboard/launch/status/` with `wc.error_message="Pool epuise"`:
      - returns 200,
      - the error message appears in the partial,
      - it is the error partial (retry mention).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    _make_wc_at_launch(
        client, cleanup=cleanup_waiting_configs,
        error_message="Pool epuise",
    )

    response = client.get("/onboard/launch/status/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert b"Pool epuise" in response.content, (
        "Expected error message 'Pool epuise' in error partial. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # On confirme bien que c'est le partial d'erreur (et pas un autre)
    # via le `data-testid` dedie. / Confirm we got the error partial via
    # the dedicated `data-testid`.
    assert b"onboard-status-error" in response.content, (
        "Expected `data-testid=onboard-status-error` marker."
    )


def test_resume_magic_link_valid_redirects_to_current_step(
    cleanup_waiting_configs,
):
    """
    GET `/onboard/resume/<signed>/` avec une signature valide produite
    par `TimestampSigner().sign(str(wc.uuid))` :
      - retourne 302 (ou 303),
      - redirige vers `/onboard/launch/` (step courante du WC).

    / GET `/onboard/resume/<signed>/` with a valid signature produced by
    `TimestampSigner().sign(str(wc.uuid))`:
      - returns 302 (or 303),
      - redirects to `/onboard/launch/` (WC's current step).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    # On ne fixe pas la session : le but du magic link est justement de
    # la (re)poser. / We don't pin the session: the magic link's job is
    # precisely to re-set it.
    unique_email = f"resume-{int(time.time() * 1000000)}@example.com"
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Resume Test",
            email=unique_email,
            dns_choice="tibillet.coop",
            email_confirmed=True,
            current_step=WaitingConfiguration.STEP_LAUNCH,
            phone="",
        )
    cleanup_waiting_configs(wc)

    signer = signing.TimestampSigner()
    signed = signer.sign(str(wc.uuid))

    response = client.get(f"/onboard/resume/{signed}/")

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/launch/", (
        f"Expected redirect to /onboard/launch/, got {response['Location']!r}"
    )


def test_resume_magic_link_invalid_returns_400():
    """
    GET `/onboard/resume/<bad>/` avec une signature invalide :
      - retourne 400,
      - rend le partial `resume_invalid.html` (data-testid present).

    / GET `/onboard/resume/<bad>/` with an invalid signature:
      - returns 400,
      - renders the `resume_invalid.html` partial (data-testid present).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    # Signature volontairement bidon : ne ressemble pas a une sortie
    # TimestampSigner. / Intentionally bogus signature: doesn't look like
    # a TimestampSigner output.
    response = client.get("/onboard/resume/garbage-not-a-real-signature/")

    assert response.status_code == 400, (
        f"Expected 400, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert b"onboard-resume-invalid" in response.content, (
        "Expected `data-testid=onboard-resume-invalid` marker."
    )


def test_launch_retry_resets_error_and_enqueues_task(cleanup_waiting_configs):
    """
    POST `/onboard/launch/retry/` :
      - retourne 200 (partial progress),
      - reset `wc.error_message=""`,
      - appelle `create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))`.

    On patche `create_tenant_from_draft.delay` pour eviter d'enqueuer
    une vraie task Celery (sinon le worker tenterait de creer un tenant
    en DB dev). / We patch `create_tenant_from_draft.delay` to avoid
    enqueuing a real Celery task.

    / POST `/onboard/launch/retry/`:
      - returns 200 (progress partial),
      - resets `wc.error_message=""`,
      - calls `create_tenant_from_draft.delay(wc_uuid=str(wc.uuid))`.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _make_wc_at_launch(
        client, cleanup=cleanup_waiting_configs,
        error_message="Erreur factice",
    )

    with patch("onboard.tasks.create_tenant_from_draft.delay") as mock_delay:
        response = client.post("/onboard/launch/retry/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    # Partial progress -> polling reactive. / Progress partial -> polling
    # reactivated.
    assert b"every 2s" in response.content

    # Reset effectif en base. / Reset effective in DB.
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.error_message == "", (
        f"Expected empty error_message after retry, got {wc.error_message!r}"
    )

    # Task re-enqueuee avec le bon UUID. / Task re-enqueued with the
    # right UUID.
    mock_delay.assert_called_once_with(wc_uuid=str(wc.uuid))
