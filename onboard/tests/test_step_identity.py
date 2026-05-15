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


# Hote HTTP de dev par defaut (cf. pattern V2 du projet). Le wizard est
# accessible depuis ROOT et depuis tous les tenants — on tape le tenant
# `lespass` qui est toujours present en DB dev.
# / Default dev HTTP host (cf. V2 project pattern). The wizard is reachable
# from ROOT and any tenant — we hit `lespass`, always present in dev DB.
DEV_HOST = "lespass.tibillet.localhost"


def test_identity_get_renders_form():
    """
    GET `/onboard/identity/` retourne 200 et un HTML contenant le titre
    "Cr..." (intl : "Creer" en FR, "Create" en EN).
    / GET `/onboard/identity/` returns 200 + HTML title starting with
    "Cr..." (i18n: "Creer" FR, "Create" EN).
    """
    client = Client(HTTP_HOST=DEV_HOST)
    response = client.get("/onboard/identity/")

    assert response.status_code == 200
    # On verifie que le titre commence bien par "Cr" : couvre les deux
    # langues du template (Creer / Create) et ne casse pas si le projet
    # ajoute d'autres traductions plus tard.
    # / Title starts with "Cr": covers FR/EN templates and won't break
    # if more translations are added later.
    assert b"Cr" in response.content


def test_identity_post_creates_wc_and_redirects_to_verify(cleanup_waiting_configs):
    """
    POST valide cree un WaitingConfiguration en schema `meta` et redirige
    vers `/onboard/verify/`. Le brouillon est marque `current_step=verify`,
    `email_confirmed=False`, et un `otp_hash` non vide est persiste.
    / Valid POST creates a draft and redirects to `/onboard/verify/`.
    Draft has `current_step=verify`, `email_confirmed=False`, non-empty
    `otp_hash`.

    Le mailer Celery est patche : on ne veut pas spammer un vrai SMTP
    en tests. La methode `.delay(...)` est juste interceptee.
    / Celery mailer is patched: we don't want to hit real SMTP in tests.
    `.delay(...)` is intercepted.
    """
    client = Client(HTTP_HOST=DEV_HOST)

    # On utilise un suffixe unique pour eviter les collisions si la DB
    # dev contient deja un WC avec cet email (cleanup precedent rate).
    # / Unique suffix to avoid colliding with stale dev DB rows.
    import time
    unique_email = f"new-{int(time.time() * 1000)}@example.com"

    # Mod 1 (feedback mainteneur 2026-05-15) : `identity` POST n'enqueue
    # PLUS le mailer OTP. L'utilisateur doit cliquer "Recevoir le code"
    # sur la step Verify. On verifie donc :
    #   - WC cree avec `current_step=verify`, `email_confirmed=False`.
    #   - `otp_hash` reste VIDE a ce stade (pas de code genere).
    #   - Le mailer N'EST PAS appele.
    # / Mod 1 (maintainer feedback): `identity` POST NO LONGER enqueues
    # the OTP mailer. User must click "Receive the code" on Verify.
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
        # Mod 1 : otp_hash reste vide tant que l'user n'a pas clique resend.
        # / Mod 1: otp_hash stays empty until user clicks resend.
        assert wc.otp_hash == "", (
            "OTP hash should be empty (Mod 1: no auto-send)."
        )
        assert wc.email_confirmed is False

    # Mod 1 : le mailer ne doit PAS avoir ete appele a ce stade.
    # / Mod 1: mailer must NOT have been called at this point.
    assert not mock_mailer.called, (
        "OTP mailer should NOT be auto-enqueued by identity (Mod 1)."
    )


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
