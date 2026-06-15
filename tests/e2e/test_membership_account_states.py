"""
Tests E2E : états d'adhésion sur le compte utilisateur (déjà active, expirée).
/ E2E tests: membership account states (already active, expired).

Conversion de tests/playwright/tests/21-membership-account-states.spec.ts

Scénario :
1. Créer un produit adhésion limité (max_per_user=1) + une adhésion valide
   pour un nouvel utilisateur via l'API v2.
2. Connecter cet utilisateur : ouvrir le produit depuis /memberships/ doit
   afficher le message "Adhésion déjà active".
3. Créer un second produit adhésion + une adhésion expirée (validUntil passé).
4. La page /my_account/membership/ doit montrer la carte expirée avec un
   lien "Renouveler" / "Renew".

/ Scenario: create a limited membership product + active membership, check
the "already active" message, then create an expired membership and check
the "Expired" card with a "Renew" link on the account page.
"""

import datetime
import os
import random
import shutil
import string

import pytest
import requests as http_requests
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# --- Configuration URL API (même logique que tests/e2e/conftest.py) ---
# La fixture conftest `create_product` ne couvre pas la création d'adhésion :
# on reconstruit ici les constantes pour appeler /api/v2/memberships/ en direct.
# / API URL configuration (same logic as tests/e2e/conftest.py).
# The conftest `create_product` fixture does not cover membership creation:
# we rebuild the constants here to call /api/v2/memberships/ directly.

SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Suffixe unique pour isoler les données du test (DB dev partagée).
    / Unique suffix to isolate test data (shared dev DB).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _create_membership_api(api_key, price_uuid, email, valid_until,
                           payment_mode="FREE"):
    """Crée une adhésion via l'API v2 (équivalent de createMembershipApi en TS).
    / Creates a membership via API v2 (equivalent of TS createMembershipApi).

    Retourne dict {ok, status, data}.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER

    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": "API",
            "familyName": "Member",
        },
        "membershipPlan": {
            "@type": "Offer",
            "identifier": price_uuid,
        },
        "validUntil": valid_until,
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "paymentMode",
                "value": payment_mode,
            },
        ],
    }

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/memberships/",
        headers=headers,
        json=payload,
        verify=False,
    )
    data = None
    try:
        data = resp.json()
    except Exception:
        pass
    return {"ok": resp.ok, "status": resp.status_code, "data": data}


def _find_price_uuid(offers, price_name):
    """Retrouve l'UUID (identifier) d'un tarif par son nom dans la réponse API.
    / Finds the price UUID (identifier) by name in the API response offers.
    """
    for offer in (offers or []):
        if offer.get("name") == price_name:
            return offer.get("identifier")
    return None


class TestMembershipAccountStates:
    """États adhésion compte : déjà active, expirée.
    / Membership account states: already has, expired.
    """

    def test_should_show_already_has_and_expired(
        self, page, create_product, django_shell, api_key, login_as
    ):
        """Adhésion active → message 'déjà active' ; adhésion expirée → carte
        'Expiré' avec lien 'Renouveler' sur /my_account/membership/.
        / Active membership shows already-has message; expired one shows
        Expired card with Renew link on the account page.
        """
        random_id = _random_id()
        user_email = f"jturbeaux+state{random_id}@pm.me"

        limited_product_name = f"Adhesion Limited {random_id}"
        limited_price_name = "Tarif Limited"

        expired_product_name = f"Adhesion Expired {random_id}"
        expired_price_name = "Tarif Expired"

        # --- Étape 1 : Créer le produit adhésion limité via API ---
        # / Step 1: Create the limited membership product via API
        limited_result = create_product(
            name=limited_product_name,
            description="Produit adhesion limite.",
            category="Membership",
            offers=[
                {"name": limited_price_name, "price": "10.00"},
            ],
        )
        assert limited_result["ok"], f"Création produit échouée: {limited_result}"
        limited_product_uuid = limited_result["uuid"]

        limited_price_uuid = _find_price_uuid(
            limited_result["offers"], limited_price_name
        )
        assert limited_price_uuid, (
            f"UUID du tarif limité introuvable: {limited_result['offers']}"
        )

        # La fixture create_product n'expose pas productMaxPerUser (le spec TS
        # l'envoyait dans additionalProperty). On pose max_per_user=1 en DB via
        # django_shell — c'est ce qui déclenche le message "déjà active".
        # NB : pas de guillemets doubles dans le code shell (échappement conftest).
        # / The create_product fixture has no productMaxPerUser option (TS spec
        # sent it via additionalProperty). We set max_per_user=1 in DB through
        # django_shell — that is what triggers the "already active" message.
        shell_output = django_shell(
            "from BaseBillet.models import Product; "
            f"Product.objects.filter(uuid='{limited_product_uuid}')"
            ".update(max_per_user=1); "
            "print('MAX_PER_USER_OK')"
        )
        assert "MAX_PER_USER_OK" in shell_output, (
            f"max_per_user non posé sur le produit: {shell_output}"
        )

        # Adhésion valide 30 jours pour l'utilisateur (paiement FREE).
        # / 30-day valid membership for the user (FREE payment).
        valid_until = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30)
        ).isoformat()
        membership_result = _create_membership_api(
            api_key=api_key,
            price_uuid=limited_price_uuid,
            email=user_email,
            valid_until=valid_until,
            payment_mode="FREE",
        )
        assert membership_result["ok"], (
            f"Création adhésion échouée: {membership_result}"
        )

        # --- Étape 2 : Connecter l'utilisateur ---
        # L'API adhésion crée l'utilisateur INACTIF (email non validé).
        # ModelBackend.get_user refuse un user inactif : la session force_login
        # serait anonyme et la vue rendrait le formulaire au lieu du message
        # "déjà active". Le spec TS passait par le lien TEST MODE qui valide
        # l'email — on reproduit cette activation en DB via django_shell.
        # / Step 2: the membership API creates the user INACTIVE (email not
        # validated). ModelBackend.get_user rejects inactive users: the
        # force_login session would be anonymous and the view would render the
        # form instead of the "already active" message. The TS spec used the
        # TEST MODE magic link which validates the email — we replicate that
        # activation in DB through django_shell.
        activation_output = django_shell(
            "from AuthBillet.models import TibilletUser; "
            f"TibilletUser.objects.filter(email='{user_email}')"
            ".update(is_active=True, email_valid=True); "
            "print('USER_ACTIVE_OK')"
        )
        assert "USER_ACTIVE_OK" in activation_output, (
            f"Activation utilisateur échouée: {activation_output}"
        )

        login_as(page, user_email)

        # --- Étape 3 : Message "Adhésion déjà active" ---
        # Sur /memberships/, ouvrir le produit limité : la vue détecte
        # max_per_user_reached et rend already_has_membership.html.
        # / Step 3: "Membership already active" message. Opening the limited
        # product renders already_has_membership.html (max_per_user reached).
        page.goto("/memberships/")
        page.wait_for_load_state("domcontentloaded")

        # Le bouton Subscribe est un hx-get : si on clique avant que HTMX ait
        # traité le DOM, aucune requête ne part et l'offcanvas s'ouvre vide.
        # On attend que HTMX soit chargé ET que la page soit complète.
        # / The Subscribe button is an hx-get: clicking before HTMX processed
        # the DOM fires no request and the offcanvas opens empty. Wait for
        # HTMX to be loaded AND the page to be complete before clicking.
        page.wait_for_function(
            "() => typeof window.htmx !== 'undefined' "
            "&& document.readyState === 'complete'"
        )

        open_button = page.locator(
            f'[data-testid="membership-open-{limited_product_uuid}"], '
            f'button[hx-get="/memberships/{limited_product_uuid}/"]'
        ).first
        open_button.click()

        already_content = page.locator("#membership-already-has-content").first
        # Re-clic de secours si le swap HTMX n'est pas arrivé (timing).
        # / Fallback re-click if the HTMX swap did not happen (timing).
        try:
            expect(already_content).to_be_visible(timeout=10_000)
        except AssertionError:
            open_button.click()
            expect(already_content).to_be_visible(timeout=10_000)

        # Assertion tolérante FR/EN — piège 9.34 de tests/PIEGES.md.
        # / FR/EN tolerant assertion — trap 9.34 in tests/PIEGES.md.
        already_text = already_content.text_content() or ""
        assert (
            "Adhésion déjà active" in already_text
            or "Membership already active" in already_text
        ), f"Message 'déjà active' absent, contenu: {already_text[:300]}"

        # --- Étape 4 : Créer une adhésion expirée ---
        # Second produit (sans limite), adhésion avec validUntil dans le passé.
        # / Step 4: Create an expired membership. Second product (no limit),
        # membership with validUntil in the past.
        expired_result = create_product(
            name=expired_product_name,
            description="Produit adhesion expiree.",
            category="Membership",
            offers=[
                {"name": expired_price_name, "price": "5.00"},
            ],
        )
        assert expired_result["ok"], f"Création produit échouée: {expired_result}"

        expired_price_uuid = _find_price_uuid(
            expired_result["offers"], expired_price_name
        )
        assert expired_price_uuid, (
            f"UUID du tarif expiré introuvable: {expired_result['offers']}"
        )

        expired_until = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=5)
        ).isoformat()
        expired_membership = _create_membership_api(
            api_key=api_key,
            price_uuid=expired_price_uuid,
            email=user_email,
            valid_until=expired_until,
            payment_mode="FREE",
        )
        assert expired_membership["ok"], (
            f"Création adhésion expirée échouée: {expired_membership}"
        )

        # --- Étape 5 : Carte expirée avec lien Renouveler ---
        # La page compte liste les adhésions : la carte expirée affiche
        # 'Expired' / 'A expiré' et un lien 'Renew' / 'Renouveler'
        # (template membership_card.html).
        # / Step 5: Expired card shows a Renew link on the account page
        # (membership_card.html template).
        page.goto("/my_account/membership/")
        page.wait_for_load_state("domcontentloaded")

        body_text = page.text_content("body") or ""

        # Le runserver de dev peut casser une socket sous charge et rendre
        # une page d'erreur transitoire (OSError Bad file descriptor).
        # Dans ce cas on recharge UNE fois avant de verifier.
        # / The dev runserver can break a socket under load and render a
        # transient error page. Reload ONCE before asserting.
        if "OSError" in body_text or "Server Error" in body_text:
            page.wait_for_timeout(2_000)
            page.goto("/my_account/membership/")
            page.wait_for_load_state("domcontentloaded")
            body_text = page.text_content("body") or ""

        # Tolérance FR/EN : 'Expired' (EN) ou 'A expiré' (trad FR du .po).
        # / FR/EN tolerance: 'Expired' (EN) or 'A expiré' (FR .po translation).
        assert "Expired" in body_text or "expiré" in body_text, (
            "La mention 'Expired' / 'expiré' devrait apparaître sur la page compte"
        )

        renew_link = page.locator(
            'a:has-text("Renew"), a:has-text("Renouveler")'
        ).first
        expect(renew_link).to_be_visible()
