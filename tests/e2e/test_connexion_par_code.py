"""
Tests E2E : connexion par code à 6 chiffres sur le guichet commun à tous les lieux.
/ E2E tests: 6-digit code login on the login desk shared by all venues.

LOCALISATION : tests/e2e/test_connexion_par_code.py

Parcours testés (TECH_DOC/SESSIONS/TODO/AUTH-connexion-par-code-achat-connecte.md, §8.2) :
1. depuis un lieu, « Se connecter » mène au guichet ; on demande un code, on tape le
   code, on revient sur le lieu, connecté ;
2. SSO : connecté sur `lespass`, on se connecte sur `festival` d'un clic, sans code ;
   puis « Me déconnecter » sur `festival` déconnecte aussi de `lespass` ;
3. « Se connecter pour réserver » : après la connexion, la page de l'événement revient
   avec le panneau de réservation ouvert.
/ Tested journeys: code login, SSO between venues, logout everywhere, booking reopen.

LE CODE : un test ne peut pas lire le mail. Après la demande de code, on remplace
l'empreinte gardée en cache par celle d'un code connu. Les clés du code vivent sur le
schéma `public` (le guichet, `AuthBillet/connexion_par_code.py`) : on les écrit dans le
contexte de `public`, avec `cle_cache` du service (jamais recopiée à la main).
/ A test cannot read the mail: the cached fingerprint is replaced by a known code's,
on the public schema, with the service's own key builder.

Prérequis : le serveur de dev tourne (lieux `lespass` et `festival`, guichet sur
`tibillet.localhost`).
"""

import re
import uuid

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import DOMAIN

# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.e2e, pytest.mark.site]

# Le code « reçu par mail », posé en cache à la place du vrai.
# / The "received by mail" code, put in the cache instead of the real one.
CODE_CONNU = "246813"

ADRESSE_DE_LESPASS = f"https://lespass.{DOMAIN}"
ADRESSE_DE_FESTIVAL = f"https://festival.{DOMAIN}"


def un_email_neuf():
    """Un email jamais vu : le compte est créé par le guichet, après le bon code.
    / A brand new email: the account is created by the desk, after the right code."""
    return f"e2e-code-{uuid.uuid4().hex[:8]}@mock.test"


def remplacer_le_code_par_un_code_connu(django_shell, email):
    """
    Remplace l'empreinte du code envoyé à `email` par celle de CODE_CONNU.
    Les clés sont écrites dans le contexte de `public` : c'est là que le guichet
    les lit (django_tenants préfixe chaque clé par le nom du schéma).
    / Replaces the fingerprint of the code sent to `email` with CODE_CONNU's,
    in the public schema context, where the desk reads it.
    """
    django_shell(
        "from django.core.cache import cache\n"
        "from AuthBillet.connexion_par_code import cle_cache\n"
        "from AuthBillet.otp_service import hash_code_otp, OTP_TTL_SECONDS\n"
        f"cle_de_l_empreinte = cle_cache('{email}', 'empreinte')\n"
        "if cache.get(cle_de_l_empreinte) is None:\n"
        "    raise RuntimeError('Aucun code en cache : la demande de code n a pas abouti.')\n"
        f"cache.set(cle_de_l_empreinte, hash_code_otp('{CODE_CONNU}'), OTP_TTL_SECONDS)\n",
        schema="public",
    )


def taper_l_email_puis_le_code(page, django_shell, email):
    """
    Sur le guichet : tape l'email, demande un code, pose le code connu, le tape.
    La page du guichet doit déjà être affichée.
    / On the desk: types the email, asks a code, sets the known code, types it.
    """
    page.wait_for_url(lambda adresse: "/sso/" in adresse, timeout=10_000)
    page.locator('[data-testid="login-email"]').fill(email)
    page.locator('[data-testid="login-submit"]').click()

    champ_du_code = page.locator('[data-testid="login-code"]')
    expect(champ_du_code).to_be_visible(timeout=10_000)

    remplacer_le_code_par_un_code_connu(django_shell, email)

    champ_du_code.fill(CODE_CONNU)
    page.locator('[data-testid="login-code-submit"]').click()


def se_connecter_sur_lespass_par_le_guichet(page, django_shell, email):
    """
    Depuis l'accueil de `lespass` (skin V2) : bouton « Connexion » de la barre,
    lien « Se connecter » du panneau, puis email et code sur le guichet.
    Rend la main une fois revenu sur `lespass`, connecté.
    / From lespass home: login panel, desk link, email and code. Returns once back.
    """
    page.goto(f"{ADRESSE_DE_LESPASS}/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="user-bar-connexion"]').click()
    lien_vers_le_guichet = page.locator('[data-testid="login-guichet"]')
    expect(lien_vers_le_guichet).to_be_visible()
    lien_vers_le_guichet.click()

    taper_l_email_puis_le_code(page, django_shell, email)

    page.wait_for_url(
        lambda adresse: (
            adresse.startswith(ADRESSE_DE_LESPASS) and "/connexion/" not in adresse
        ),
        timeout=15_000,
    )
    page.wait_for_load_state("networkidle")


# --------------------------------------------------------------------------
# 1. Connexion par le guichet
# / 1. Login through the desk
# --------------------------------------------------------------------------


def test_se_connecter_par_le_guichet_avec_le_code_recu(page, django_shell):
    """
    « Se connecter » sur `lespass` mène au guichet. Après l'email et le bon code, la
    personne revient sur `lespass`, connectée, avec un compte activé créé pour elle.
    / Login on lespass goes to the desk; after the right code, back on lespass, logged in.
    """
    email = un_email_neuf()

    se_connecter_sur_lespass_par_le_guichet(page, django_shell, email)

    # La barre du skin V2 montre « Mon espace » au lieu de « Connexion ».
    # / The V2 bar shows "My space" instead of "Login".
    expect(page.locator('[data-testid="user-bar-mon-espace"]')).to_be_visible()
    expect(page.locator('[data-testid="user-bar-connexion"]')).to_have_count(0)

    etat_du_compte = django_shell(
        "from AuthBillet.models import TibilletUser\n"
        f"compte = TibilletUser.objects.get(email='{email}')\n"
        "print(f'ACTIF={compte.is_active} EMAIL_VALIDE={compte.email_valid}')"
    )
    assert "ACTIF=True EMAIL_VALIDE=True" in etat_du_compte, etat_du_compte


# --------------------------------------------------------------------------
# 2. SSO entre deux lieux, puis déconnexion de partout
# / 2. SSO between two venues, then logout everywhere
# --------------------------------------------------------------------------


def test_connecte_sur_lespass_on_entre_sur_festival_sans_code_puis_on_sort_de_partout(
    page, django_shell
):
    """
    Connectée sur `lespass` (donc sur le guichet), la personne clique « Se connecter »
    sur `festival` : elle revient connectée, sans rien taper. Puis « Me déconnecter » sur
    `festival` la déconnecte aussi de `lespass`.
    / Logged in on lespass, one click logs in on festival without a code; logging out
    on festival also logs out of lespass.
    """
    email = un_email_neuf()
    se_connecter_sur_lespass_par_le_guichet(page, django_shell, email)
    expect(page.locator('[data-testid="user-bar-mon-espace"]')).to_be_visible()

    # --- SSO : « Se connecter » sur festival (skin faire_festival) ---
    # On note toute page du guichet qui demanderait un email : il ne doit y en avoir aucune.
    # / Record any desk page asking for an email: there must be none.
    pages_du_guichet_avec_formulaire = []
    page.on(
        "response",
        lambda reponse: (
            pages_du_guichet_avec_formulaire.append(reponse.url)
            if "/sso/code/" in reponse.url
            else None
        ),
    )
    page.goto(f"{ADRESSE_DE_FESTIVAL}/")
    page.wait_for_load_state("networkidle")
    page.locator('button[data-bs-target="#loginPanel"]:visible').first.click()
    lien_vers_le_guichet = page.locator('[data-testid="login-guichet"]')
    expect(lien_vers_le_guichet).to_be_visible()
    lien_vers_le_guichet.click()

    page.wait_for_url(
        lambda adresse: (
            adresse.startswith(ADRESSE_DE_FESTIVAL) and "/connexion/" not in adresse
        ),
        timeout=15_000,
    )
    page.wait_for_load_state("networkidle")
    assert pages_du_guichet_avec_formulaire == [], (
        f"Le guichet a redemandé un code : {pages_du_guichet_avec_formulaire}"
    )
    # Connectée sur festival : le menu du compte porte le bouton « Me déconnecter ».
    # / Logged in on festival: the account menu holds the logout button.
    bouton_de_deconnexion = page.locator('[data-testid="bouton-deconnexion"]').first
    expect(bouton_de_deconnexion).to_be_attached()

    # --- Déconnexion de partout, depuis festival ---
    # Le bouton est dans un menu déroulant fermé : on poste son formulaire
    # (POST + jeton CSRF), comme le ferait le clic.
    # / The button sits in a closed dropdown: submit its form, as a click would.
    with page.expect_navigation():
        bouton_de_deconnexion.evaluate("bouton => bouton.form.requestSubmit(bouton)")
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-testid="bouton-deconnexion"]')).to_have_count(0)

    # Sur lespass, la session est fermée elle aussi.
    # / On lespass, the session is closed too.
    page.goto(f"{ADRESSE_DE_LESPASS}/")
    page.wait_for_load_state("networkidle")
    expect(page.locator('[data-testid="user-bar-connexion"]')).to_be_visible()
    expect(page.locator('[data-testid="user-bar-mon-espace"]')).to_have_count(0)


# --------------------------------------------------------------------------
# 3. « Se connecter pour réserver » rouvre le panneau de réservation
# / 3. "Log in to book" reopens the booking panel
# --------------------------------------------------------------------------


@pytest.mark.billetterie
def test_se_connecter_pour_reserver_rouvre_le_panneau_de_reservation(
    page, django_shell, e2e_slugs
):
    """
    Anonyme sur la page d'un événement : « Se connecter pour réserver » ouvre le panneau
    de connexion. Après le code, la page de l'événement revient avec le panneau de
    réservation ouvert, et le bouton « Payer maintenant » à la place du bouton de connexion.
    / Anonymous on an event page: after login, the event page comes back with the
    booking panel open and the submit button.
    """
    email = un_email_neuf()
    slug_de_l_evenement = e2e_slugs["event_payant_slug"]

    page.goto(f"{ADRESSE_DE_LESPASS}/event/{slug_de_l_evenement}/")
    page.wait_for_load_state("networkidle")
    page.locator('[data-testid="booking-open-panel"]').click()
    expect(page.locator("#reservation_form")).to_be_visible(timeout=5_000)

    page.locator('[data-testid="booking-login"]').click()
    expect(page.locator("#loginPanel")).to_have_class(
        re.compile(r"\bshow\b"), timeout=5_000
    )
    page.locator('[data-testid="login-guichet"]').click()

    taper_l_email_puis_le_code(page, django_shell, email)

    page.wait_for_url(
        lambda adresse: f"/event/{slug_de_l_evenement}/" in adresse, timeout=15_000
    )
    page.wait_for_load_state("networkidle")
    expect(page.locator("#bookingPanel")).to_have_class(
        re.compile(r"\bshow\b"), timeout=5_000
    )
    expect(page.locator('[data-testid="booking-submit"]')).to_be_visible()
    expect(page.locator('[data-testid="booking-login"]')).to_have_count(0)
