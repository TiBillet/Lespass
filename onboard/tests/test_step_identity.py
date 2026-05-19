"""
Tests de la step 1 — Identite (Task 10).
/ Tests for wizard step 1 — Identity (Task 10).

LOCALISATION: onboard/tests/test_step_identity.py

On verifie :
  1. GET `/onboard/identity/` rend le formulaire (200, titre present).
  2. POST valide -> redirige vers `/onboard/verify/`, cree un brouillon
     dans le schema `meta` avec `current_step="verify"`, un `otp_hash`
     non vide et `email_confirmed=False`.
  3. POST avec `?invite=<code>` -> attache l'invitation au brouillon.

Note branche `main-wizard` : `fedow_core.Federation` n'existe pas, et la
FK `OnboardInvitation.federation` est commentee. Le test 3 cree donc
l'invitation sans param `federation` — la cle attendue est uniquement
`wc.invitation_id == inv.id` + `wc.invitation.code == inv.code`.

/ Branch `main-wizard` note: `fedow_core.Federation` does not exist, and
`OnboardInvitation.federation` FK is commented out. Test 3 creates the
invitation without that param — expected assertion is just
`wc.invitation_id == inv.id` + matching code.

PIEGE : le mailer Celery `onboard_otp_mailer.delay(...)` est appele dans
le POST identity. En tests, on patch la task pour eviter tout appel SMTP
reel et garder le test rapide / deterministe.
/ PITFALL: the Celery mailer is enqueued by the identity POST. We patch
it in tests to avoid any real SMTP call and keep tests fast.
"""

from unittest.mock import patch

import pytest
from django.test import Client
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


def test_identity_get_renders_form():
    """
    GET `/onboard/identity/` retourne 200 et un HTML contenant le formulaire
    identifie par `data-testid="onboard-identity-form"`.

    NOTE 2026-05-15 : avant on cherchait `b"Cr"` (debut de "Creer"/"Create").
    Le titre principal a ete retire du content (deja porte par l'eyebrow du
    panneau gauche), donc on assert maintenant sur le data-testid du form
    qui est plus stable et plus specifique.

    / GET `/onboard/identity/` returns 200 + HTML containing the form
    identified by `data-testid="onboard-identity-form"`. The previous
    `b"Cr"` assert was tied to the main title (now removed because already
    shown in the left panel eyebrow); we now assert on the form's
    data-testid which is more stable and specific.
    """
    client = Client(HTTP_HOST=DEV_HOST)
    response = client.get("/onboard/identity/")

    assert response.status_code == 200
    # data-testid stable : `onboard-identity-form` est l'identifiant E2E
    # du <form> principal (cf. djc skill : data-testid sur tout element
    # interactif). / Stable testid: identifies the main form (cf. djc).
    assert b'data-testid="onboard-identity-form"' in response.content


def test_identity_post_creates_wc_and_redirects_to_verify(cleanup_waiting_configs):
    """
    POST valide cree un WaitingConfiguration en schema `meta` et redirige
    vers `/onboard/verify/`. Le brouillon est marque `current_step=verify`,
    `email_confirmed=False`, et un `otp_hash` non vide est persiste +
    le mailer Celery est appele.

    Le mailer Celery est patche : on ne veut pas spammer un vrai SMTP
    en tests. La methode `.delay(...)` est juste interceptee.

    HISTORIQUE : avant le refacto 2026-05-15 (Mod 1), `identity` POST
    n'envoyait PAS d'OTP — l'utilisateur devait cliquer "Recevoir le
    code" sur Verify. Friction UX. On a re-active l'envoi automatique,
    avec garde-fous serveur (cooldown 60s + rate-limit IP) sur le
    bouton "Renvoyer".

    / Valid POST creates a draft and redirects to `/onboard/verify/`.
    Draft has `current_step=verify`, `email_confirmed=False`, non-empty
    `otp_hash` AND the Celery mailer is called.

    HISTORY: before the 2026-05-15 refactor (Mod 1), `identity` POST did
    NOT send an OTP — user had to click "Receive code" on Verify. UX
    friction. We re-enabled auto-send with server guards on Resend.
    """
    client = Client(HTTP_HOST=DEV_HOST)

    # On utilise un suffixe unique pour eviter les collisions si la DB
    # dev contient deja un WC avec cet email (cleanup precedent rate).
    # / Unique suffix to avoid colliding with stale dev DB rows.
    import time
    unique_email = f"new-{int(time.time() * 1000)}@example.com"

    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock_mailer:
        response = client.post("/onboard/identity/", data={
            "email": unique_email,
            "email_confirm": unique_email,
            "first_name": "Jonas",
            "last_name": "Test",
            "name": "Mon Lieu Test",
            "dns_choice": "tibillet.coop",
            "cgu": "on",
        })

    assert response.status_code in (302, 303), (
        f"Expected 302/303, got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )
    assert response["Location"] == "/onboard/verify/"

    # Le WC doit exister en schema `meta` (modele SHARED, schema-bound).
    # / WC must exist in `meta` schema (SHARED model, schema-bound).
    with schema_context("meta"):
        wc = WaitingConfiguration.objects.filter(email=unique_email).first()
        assert wc is not None, "WaitingConfiguration not created."
        cleanup_waiting_configs(wc)
        assert wc.current_step == "verify"
        # OTP envoye automatiquement : hash + expires_at + sent_at remplis.
        # / OTP auto-sent: hash + expires_at + sent_at populated.
        assert wc.otp_hash != "", (
            "OTP hash should be populated (auto-send after identity POST)."
        )
        assert wc.otp_expires_at is not None, (
            "otp_expires_at should be set (auto-send)."
        )
        assert wc.otp_sent_at is not None, (
            "otp_sent_at should be set (anti-spam cooldown tracking)."
        )
        assert wc.email_confirmed is False
        # Premier envoi : ne doit PAS incrementer otp_resend_count
        # (qui est reserve aux resends explicites via le bouton).
        # / First send: must NOT bump otp_resend_count (reserved for
        # explicit resends via the Resend button).
        assert wc.otp_resend_count == 0

    # Le mailer Celery doit avoir ete enqueue avec le wc_uuid + un OTP clair.
    # / Celery mailer must have been enqueued with the wc_uuid + clear OTP.
    mock_mailer.assert_called_once()
    call_kwargs = mock_mailer.call_args.kwargs
    assert call_kwargs["wc_uuid"] == str(wc.uuid)
    assert call_kwargs["otp_clair"]  # 6 chiffres non vide / 6-digit non-empty


def test_identity_post_with_invitation_attaches_it(
    cleanup_waiting_configs, cleanup_invitations,
):
    """
    POST `/onboard/identity/?invite=<code>` attache l'OnboardInvitation
    correspondante au brouillon cree.

    Sur cette branche `main-wizard`, `OnboardInvitation.federation` est
    commentee (cf. onboard/models.py). On cree donc l'invitation sans
    cette FK : `invited_by_user` + `invited_by_tenant` suffisent.

    / POST `/onboard/identity/?invite=<code>` attaches the OnboardInvitation
    to the created draft. On `main-wizard`, the `federation` FK is
    commented out, so the invitation is created without it.
    """
    from AuthBillet.models import TibilletUser
    from Customers.models import Client as TenantClient
    from onboard.models import OnboardInvitation

    # On a besoin d'un utilisateur existant + d'un tenant non-ROOT.
    # / We need an existing user + a non-ROOT tenant.
    inviter_user = TibilletUser.objects.first()
    assert inviter_user is not None, (
        "Test requires at least one TibilletUser in dev DB."
    )
    inviting_tenant = TenantClient.objects.exclude(
        categorie=TenantClient.ROOT,
    ).first()
    assert inviting_tenant is not None, (
        "Test requires at least one non-ROOT tenant in dev DB."
    )

    inv = OnboardInvitation.objects.create(
        invited_by_user=inviter_user,
        invited_by_tenant=inviting_tenant,
    )
    cleanup_invitations(inv)

    client = Client(HTTP_HOST=DEV_HOST)

    import time
    unique_email = f"inv-{int(time.time() * 1000)}@example.com"

    with patch("onboard.tasks.onboard_otp_mailer.delay"):
        response = client.post(
            f"/onboard/identity/?invite={inv.code}",
            data={
                "email": unique_email,
                "email_confirm": unique_email,
                "first_name": "I",
                "last_name": "N",
                "name": "Lieu invite",
                "dns_choice": "tibillet.coop",
                "cgu": "on",
            },
        )

    assert response.status_code in (302, 303)

    with schema_context("meta"):
        wc = WaitingConfiguration.objects.filter(email=unique_email).first()
        assert wc is not None, "WC not created for invited flow."
        cleanup_waiting_configs(wc)
        assert wc.invitation_id == inv.pk, (
            f"Expected invitation_id={inv.pk}, got {wc.invitation_id}."
        )
        assert wc.invitation.code == inv.code


def test_identity_post_existing_tenant_name_returns_422(cleanup_waiting_configs):
    """
    POST `/onboard/identity/` avec un nom (`name`) qui matche deja un
    tenant existant (case-insensitive) -> 422 + erreur sur `name`.

    On verifie l'UX : l'utilisateur apprend des la step 1 que le nom est
    pris, sans avoir a parcourir les 6 etapes pour decouvrir l'echec en
    Launch (ou TenantCreateValidator.create_tenant raise).

    On utilise un tenant existant en DB dev (`lespass`) qui est toujours
    la. Le check serializer fait `iexact` -> on tape "LESPASS" (casse
    differente) pour valider que le check est case-insensitive. Le mailer
    OTP est patche par defense (ne devrait pas etre appele si validation
    echoue, mais on assure).

    / POST identity with a `name` matching an existing tenant (case-
    insensitive) -> 422 + error on `name`. UX: user learns at step 1, no
    need to walk through 6 steps before discovering at Launch. We hit the
    always-present `lespass` tenant with mixed case "LESPASS" to verify
    the iexact lookup. Mailer is patched defensively.
    """
    client = Client(HTTP_HOST=DEV_HOST)

    import time
    unique_email = f"taken-{int(time.time() * 1000)}@example.com"

    with patch("onboard.tasks.onboard_otp_mailer.delay") as mock_mailer:
        response = client.post("/onboard/identity/", data={
            "email": unique_email,
            "email_confirm": unique_email,
            "first_name": "Jonas",
            "last_name": "Test",
            "name": "LESPASS",  # Case differente du tenant existant `lespass`.
            "dns_choice": "tibillet.coop",
            "cgu": "on",
        })

    assert response.status_code == 422, (
        f"Expected 422 (name taken), got {response.status_code}. "
        f"Body excerpt: {response.content[:300]!r}"
    )

    # L'erreur doit pointer specifiquement le champ `name`.
    # / Error must specifically target the `name` field.
    assert b"name" in response.content, (
        "Response should mention the `name` field error."
    )

    # Aucun WC ne doit avoir ete cree (validation a echoue avant create()).
    # / No WC should have been created (validation failed before create()).
    with schema_context("meta"):
        wc_cree = WaitingConfiguration.objects.filter(email=unique_email).first()
        if wc_cree:
            cleanup_waiting_configs(wc_cree)
        assert wc_cree is None, (
            "WC should NOT be created when name validation fails."
        )

    # Defense : le mailer OTP n'a pas ete enqueue puisque validation a echoue.
    # / Defensive: mailer OTP not enqueued since validation failed.
    assert not mock_mailer.called, (
        "OTP mailer should NOT be enqueued when serializer validation fails."
    )


def test_identity_post_rate_limit_429_after_5_calls_per_minute(cleanup_waiting_configs):
    """
    Regression : `IdentityPostRateThrottle` (5/min/IP) bloque silencieusement
    le 6e POST identity dans la meme minute depuis la meme IP. Friction zero
    pour user normal (qui POST 1 fois). Bloque un bot single-IP qui itere.

    Le throttle ne s applique qu au POST (cf. `allow_request` du throttle) :
    un user qui refresh le GET ne consomme pas le quota.

    / Regression: `IdentityPostRateThrottle` (5/min/IP) silently blocks
    the 6th identity POST in the same minute from the same IP. Zero
    friction for normal user, blocks single-IP bot.
    """
    from django.core.cache import cache
    # Reset compteur DRF (cle cache interne basee sur scope + IP).
    # / Reset DRF counter (cache key based on scope + IP).
    cache.clear()

    client = Client(HTTP_HOST=DEV_HOST)

    import time
    base_email = f"throttle-{int(time.time() * 1000)}"

    # 5 POST consecutifs depuis la meme IP : doivent passer (avec validation
    # qui peut faire 422 ou 302 mais PAS 429). On utilise un email/nom valide
    # pour un succes complet (302 vers verify) sur les 5 premiers.
    # / 5 consecutive POSTs from same IP: must NOT hit 429.
    with patch("onboard.tasks.onboard_otp_mailer.delay"):
        first_5_statuses = []
        for i in range(5):
            unique_email = f"{base_email}-{i}@example.com"
            response = client.post("/onboard/identity/", data={
                "email": unique_email,
                "email_confirm": unique_email,
                "first_name": "Bot",
                "last_name": f"Number{i}",
                "name": f"BotLieu-{base_email}-{i}",
                "dns_choice": "tibillet.coop",
                "cgu": "on",
            })
            first_5_statuses.append(response.status_code)

            # Cleanup au fur et a mesure pour eviter pollution dev DB.
            with schema_context("meta"):
                wc = WaitingConfiguration.objects.filter(email=unique_email).first()
                if wc:
                    cleanup_waiting_configs(wc)

        # Aucun des 5 ne doit etre 429 (sous le quota).
        # / None of the first 5 should be 429 (under quota).
        assert all(s != 429 for s in first_5_statuses), (
            f"Aucun des 5 premiers POST ne doit etre throttle. Statuses: {first_5_statuses}"
        )

        # 6e POST : doit etre 429 (over quota).
        # / 6th POST: must be 429 (over quota).
        response_6 = client.post("/onboard/identity/", data={
            "email": f"{base_email}-6@example.com",
            "email_confirm": f"{base_email}-6@example.com",
            "first_name": "Bot",
            "last_name": "Number6",
            "name": f"BotLieu-{base_email}-6",
            "dns_choice": "tibillet.coop",
            "cgu": "on",
        })

    assert response_6.status_code == 429, (
        f"6e POST identity dans la meme minute doit etre throttled (429), "
        f"recu {response_6.status_code}."
    )

