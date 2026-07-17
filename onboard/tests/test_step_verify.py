"""
Tests de la step 2 — Verify OTP + resend (Task 11).
/ Tests for wizard step 2 — Verify OTP + resend (Task 11).

LOCALISATION: onboard/tests/test_step_verify.py

On verifie :
  1. POST avec OTP correct -> 302/303 + brouillon a `current_step=place`
     et `email_confirmed=True`.
  2. POST avec OTP errone -> 422 + `otp_attempts` incremente.
  3. POST quand `otp_attempts >= 5` -> 422 + reponse contient "locked".
  4. POST `/onboard/resend-otp/` -> 200 + mailer Celery appele une fois.

/ We verify:
  1. POST with correct OTP -> 302/303 + draft is at `current_step=place`
     and `email_confirmed=True`.
  2. POST with wrong OTP -> 422 + `otp_attempts` incremented.
  3. POST while `otp_attempts >= 5` -> 422 + "locked" in body.
  4. POST `/onboard/resend-otp/` -> 200 + Celery mailer called once.

PIEGE : bcrypt N'EST PAS installe sur la branche `main-wizard`. Le helper
`_create_wc_with_otp` du plan utilise `bcrypt.hashpw` ; on l'adapte ici
pour utiliser `django.contrib.auth.hashers.make_password` (PBKDF2-SHA256)
qui est le hasher cible des services OTP du projet.
/ PITFALL: bcrypt is NOT installed on `main-wizard`. The plan's helper
uses `bcrypt.hashpw`; we adapt it to use Django's `make_password`
(PBKDF2-SHA256) which is the actual hasher used by the project's OTP
services.

PIEGE : le mailer Celery `onboard_otp_mailer.delay(...)` est appele dans
le POST `resend-otp`. On le patche pour eviter tout appel SMTP reel.
/ PITFALL: the Celery mailer is enqueued by the resend POST. We patch it
to avoid any real SMTP call.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.test import Client, override_settings
from django.utils import timezone
from django_tenants.utils import schema_context

from MetaBillet.models import WaitingConfiguration


# Tous les tests de ce module sont marques `onboard` (cf. pytest.ini).
# / All tests here are marked `onboard` (cf. pytest.ini).
pytestmark = pytest.mark.onboard


# Hote HTTP de dev : on cible le tenant ROOT car le wizard ne tourne plus
# que depuis ROOT (decision mainteneur 2026-05-16, dispatch() du ViewSet
# redirige tout acces depuis un tenant). Le domaine ROOT en dev est
# `www.tibillet.localhost` (cf. fixture install.py).
# / Dev host: target ROOT tenant since the wizard only runs on ROOT
# (maintainer decision 2026-05-16). ROOT dev domain is `www.tibillet.localhost`.
DEV_HOST = "tibillet.localhost"


# ---------------------------------------------------------------------------
# Helpers locaux. / Local helpers.
# ---------------------------------------------------------------------------


def _create_wc_with_otp(client, otp_clair="123456", cleanup=None):
    """
    Cree un WaitingConfiguration en schema `meta` avec un hash OTP PBKDF2
    pre-calcule, et fixe la session Django du `client` de test sur ce WC.

    On utilise `make_password` (PBKDF2-SHA256) au lieu de bcrypt car bcrypt
    n'est pas installe sur cette branche. C'est aussi le hasher utilise par
    `onboard.services.generate_otp`.

    / Create a WaitingConfiguration in the `meta` schema with a pre-computed
    PBKDF2 OTP hash, and set the Django session of the test `client` to
    point at this WC.

    We use `make_password` (PBKDF2-SHA256) instead of bcrypt because bcrypt
    isn't installed on this branch. It's also the hasher used by
    `onboard.services.generate_otp`.

    :param client: instance de `django.test.Client`.
    :param otp_clair: code OTP a hasher (str, par defaut "123456").
    :param cleanup: fixture `cleanup_waiting_configs` (callable).
    :return: instance WaitingConfiguration creee.
    """
    # Suffixe unique pour eviter les collisions si la DB dev a deja un WC
    # avec un email similaire. / Unique suffix to avoid collisions in dev DB.
    import time
    unique_email = f"verify-{int(time.time() * 1000000)}@example.com"

    otp_hash = make_password(otp_clair)
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.create(
            organisation="Verify Test",
            email=unique_email,
            dns_choice="tibillet.localhost",
            otp_hash=otp_hash,
            otp_expires_at=timezone.now() + timedelta(minutes=10),
            current_step=WaitingConfiguration.STEP_VERIFY,
            phone="",
        )
    if cleanup is not None:
        cleanup(wc)

    # Fixe l'UUID dans la session du client de test. Django `Client.session`
    # est une propriete : on doit la copier dans une variable locale,
    # modifier, puis sauvegarder explicitement (sinon les changements ne
    # sont pas persistes vers le cookie de session).
    # / Pin the UUID in the test client's session. `Client.session` is a
    # property: copy to local, mutate, then save explicitly.
    session = client.session
    session["onboard_wc_uuid"] = str(wc.uuid)
    session.save()
    return wc


# ---------------------------------------------------------------------------
# Tests. / Tests.
# ---------------------------------------------------------------------------


def test_verify_correct_otp_passes_to_place(cleanup_waiting_configs):
    """
    POST `/onboard/verify/` avec le bon OTP redirige (302/303) vers
    `/onboard/place/`. Le brouillon est mis a jour :
      - `email_confirmed=True`
      - `current_step="place"`
      - `otp_hash=""` (purge)
    Et l'utilisateur Django est LOGGUE (refacto 2026-05-15) :
      - `request.user.is_authenticated` apres la requete.
      - User TibilletUser cree avec `email_valid=True` + `is_active=True`.

    / POST `/onboard/verify/` with the correct OTP redirects (302/303) to
    `/onboard/place/`. Updates draft fields AND logs the user in
    (2026-05-15 refactor): post-verify steps require `is_authenticated`.
    """
    from django.contrib.auth import get_user_model

    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "123456", cleanup=cleanup_waiting_configs)

    response = client.post("/onboard/verify/", data={"otp": "123456"})

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/venue/"

    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.email_confirmed is True
    assert wc.current_step == WaitingConfiguration.STEP_VENUE
    assert wc.otp_hash == ""

    # User TibilletUser doit avoir ete cree avec email_valid=True + is_active=True.
    # / TibilletUser must have been created with email_valid=True + is_active=True.
    User = get_user_model()
    user = User.objects.filter(email=wc.email).first()
    assert user is not None, (
        "TibilletUser doit etre cree au verify success."
    )
    assert user.email_valid is True, (
        "user.email_valid doit passer a True (preuve OTP)."
    )
    assert user.is_active is True, (
        "user.is_active doit passer a True (sinon login impossible)."
    )

    # Login Django : la session client doit avoir le cookie auth.
    # On verifie via une 2e requete : si on lance un GET sur /onboard/place/
    # apres verify success, on doit etre authentifie (status != redirect identity).
    # / Verify Django session has auth cookie: a follow-up GET to /onboard/place/
    # after verify success should be authenticated (no redirect to identity).
    response_place = client.get("/onboard/place/")
    assert response_place.status_code == 200, (
        f"Apres verify success, GET /onboard/place/ doit etre 200 (user "
        f"loggue), recu {response_place.status_code}. Si redirect identity, "
        f"login post-verify a echoue."
    )


@override_settings(DEBUG=False)
def test_verify_wrong_otp_increments_attempts(cleanup_waiting_configs):
    """
    POST `/onboard/verify/` avec un mauvais OTP renvoie 422 et incremente
    `otp_attempts` (mais ne marque pas l'email comme confirme).
    / POST `/onboard/verify/` with a wrong OTP returns 422 and increments
    `otp_attempts` (but does NOT mark email as confirmed).

    NOTE : `@override_settings(DEBUG=False)` est obligatoire ici car la vue
    `verify` bypass entierement la verification en mode DEBUG (Mod 2,
    feedback mainteneur 2026-05-15). Sans ca le test passerait/casserait
    selon l'env.
    / `@override_settings(DEBUG=False)` is required because `verify`
    bypasses verification in DEBUG mode (Mod 2 — maintainer feedback).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "123456", cleanup=cleanup_waiting_configs)

    response = client.post("/onboard/verify/", data={"otp": "999999"})

    assert response.status_code == 422
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.otp_attempts == 1
    assert wc.email_confirmed is False
    assert wc.current_step == WaitingConfiguration.STEP_VERIFY


@override_settings(DEBUG=False)
def test_verify_locks_after_5_attempts(cleanup_waiting_configs):
    """
    Quand `otp_attempts >= 5`, le compte est verrouille : 422 + reponse
    contient le mot "locked" (ou la traduction FR "verrou").
    / When `otp_attempts >= 5`, account is locked: 422 + body contains
    "locked" (or the FR translation "verrou").

    NOTE : `@override_settings(DEBUG=False)` — cf. test ci-dessus.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "123456", cleanup=cleanup_waiting_configs)

    # Met directement `otp_attempts=5` (simulate 5 essais rates precedents).
    # / Directly set `otp_attempts=5` (simulate 5 previous wrong attempts).
    with schema_context("meta"):
        WaitingConfiguration.objects.filter(uuid=wc.uuid).update(otp_attempts=5)

    response = client.post("/onboard/verify/", data={"otp": "123456"})

    assert response.status_code == 422
    body_lower = response.content.lower()
    assert b"locked" in body_lower or b"verrou" in body_lower, (
        f"Expected 'locked' or 'verrou' in body, got: {response.content[:500]!r}"
    )


def test_verify_debug_bypass_accepts_any_code(cleanup_waiting_configs):
    """
    Mod 2 (feedback mainteneur 2026-05-15) : en mode `settings.DEBUG=True`,
    n'importe quel code 6 chiffres est accepte sans verification. Permet
    de progresser dans le wizard sans worker Celery actif.
    / Mod 2: in `settings.DEBUG=True`, any 6-digit code is accepted
    without verification. Lets the user progress without a running
    Celery worker.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "123456", cleanup=cleanup_waiting_configs)

    # Bypass actif : on poste un code INCORRECT et on s'attend a un succes.
    # / Bypass active: post a WRONG code and expect success.
    with override_settings(DEBUG=True):
        response = client.post("/onboard/verify/", data={"otp": "999999"})

    assert response.status_code in (302, 303), (
        f"Expected redirect with DEBUG bypass, got {response.status_code}."
    )
    assert response["Location"] == "/onboard/venue/"
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.email_confirmed is True
    assert wc.current_step == WaitingConfiguration.STEP_VENUE


def test_resend_otp_regenerates(cleanup_waiting_configs):
    """
    POST `/onboard/resend-otp/` retourne 200, regenere le code OTP cote
    brouillon, et enfile une nouvelle task Celery `onboard_otp_mailer`.

    Le mailer Celery est patche pour eviter tout appel SMTP reel.
    / POST `/onboard/resend-otp/` returns 200, regenerates the OTP on the
    draft, and enqueues a new `onboard_otp_mailer` Celery task. The mailer
    is patched to avoid any real SMTP call.
    """
    # Cle de cache vide -> pas de rate-limit. On purge au cas ou un test
    # precedent aurait ecrit. / Empty cache key -> no rate-limit. Purge in
    # case a previous test wrote.
    from django.core.cache import cache
    cache.delete("onboard:resend:127.0.0.1")
    cache.delete("onboard:resend:unknown")

    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "111111", cleanup=cleanup_waiting_configs)
    initial_hash = wc.otp_hash

    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock_mailer:
        response = client.post("/onboard/resend-otp/")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    mock_mailer.assert_called_once()

    # Le hash en base a change (nouveau code genere).
    # / The stored hash has changed (new code generated).
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.otp_hash != initial_hash
    assert wc.otp_attempts == 0
    assert wc.otp_resend_count == 1
    # `otp_sent_at` doit avoir ete mis a jour (sert au cooldown).
    # / `otp_sent_at` must have been updated (used by cooldown).
    assert wc.otp_sent_at is not None


def test_resend_otp_cooldown_blocks_immediate_resend(cleanup_waiting_configs):
    """
    POST `/onboard/resend-otp/` deux fois de suite (sans laisser passer le
    cooldown 60s) : la 2e demande renvoie 429 + partial cooldown, et NE
    re-genere PAS l'OTP cote brouillon (otp_hash inchange).

    Ce cooldown est COMPLEMENTAIRE au rate-limit IP (3/h) : il empeche un
    user de double-cliquer accidentellement sur "Renvoyer".

    / Two POSTs to `/onboard/resend-otp/` in less than 60s: the second
    one returns 429 + cooldown partial, and does NOT regenerate the OTP
    on the draft. This cooldown complements the per-IP rate-limit (3/h):
    it prevents an accidental double-click on Resend.
    """
    from django.core.cache import cache
    cache.delete("onboard:resend:127.0.0.1")
    cache.delete("onboard:resend:unknown")

    client = Client(HTTP_HOST=DEV_HOST)
    wc = _create_wc_with_otp(client, "111111", cleanup=cleanup_waiting_configs)

    # 1er resend : OK (otp_sent_at etait None, pas de cooldown).
    # / 1st resend: OK (otp_sent_at was None, no cooldown).
    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock_mailer:
        first_response = client.post("/onboard/resend-otp/")
    assert first_response.status_code == 200
    mock_mailer.assert_called_once()

    with schema_context("meta"):
        wc.refresh_from_db()
    hash_after_first = wc.otp_hash

    # 2e resend immediat : doit etre bloque par le cooldown 60s.
    # / Immediate 2nd resend: must be blocked by the 60s cooldown.
    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock_mailer_2:
        second_response = client.post("/onboard/resend-otp/")
    assert second_response.status_code == 429, (
        f"Expected 429 (cooldown), got {second_response.status_code}. "
        f"Body excerpt: {second_response.content[:300]!r}"
    )
    assert b"onboard-verify-resend-cooldown" in second_response.content
    # Le mailer ne doit PAS avoir ete appele lors du 2e resend.
    # / Mailer must NOT have been called on the 2nd resend.
    assert not mock_mailer_2.called, (
        "Mailer should NOT be enqueued during cooldown."
    )

    # Le hash en base ne doit PAS avoir change (pas de regeneration).
    # / The stored hash must NOT have changed (no regeneration).
    with schema_context("meta"):
        wc.refresh_from_db()
    assert wc.otp_hash == hash_after_first, (
        "OTP hash must stay unchanged when cooldown blocks the resend."
    )
