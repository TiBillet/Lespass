"""
Tests E2E : annulation d'un paiement récurrent depuis le compte utilisateur.
/ E2E tests: cancellation of a recurring payment from the user account.

Conversion de tests/playwright/tests/22-membership-recurring-cancel.spec.ts

Ce test vérifie le flow complet :
/ This test verifies the complete flow:
1. Création d'un produit d'adhésion récurrente (mensuelle) via l'API
2. Création d'une adhésion AUTO avec stripe_id_subscription simulé via l'API
3. Connexion en tant qu'utilisateur
4. Le bouton "Annuler le prélèvement automatique" est visible sur /my_account/membership/
5. Un clic sur ce bouton affiche un message d'erreur (le sub_test est fictif, Stripe rejette)

/ 1. Create a recurring monthly membership product via API
  2. Create an AUTO membership with a simulated stripe_id_subscription via API
  3. Log in as user
  4. The "Cancel automatic debit" button is visible on /my_account/membership/
  5. Clicking the button shows an error message (fake sub_test, Stripe rejects)
"""

import datetime
import os
import random
import re
import shutil
import string

import pytest
import requests as http_requests
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Même logique que conftest.py : depuis le container on passe par le Docker
# gateway (Traefik) avec un header Host ; depuis l'hôte on utilise l'URL directe.
# / Same logic as conftest.py: from container go through Docker gateway (Traefik)
# with Host header; from host use direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = (
    f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
)
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Génère un suffixe court unique (DB dev partagée, pas de rollback).
    / Generates a short unique suffix (shared dev DB, no rollback).
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification pour l'API v2.
    / Builds authentication headers for the API v2.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_membership_api_with_sub(
    api_key,
    price_uuid,
    email,
    first_name="Auto",
    last_name="Test",
    payment_mode="FREE",
    valid_until=None,
    override_status=None,
    stripe_subscription_id=None,
):
    """Crée une adhésion via POST /api/v2/memberships/ avec des champs optionnels
    stripeSubscriptionId et status (override admin).
    Équivalent de createMembershipApi dans utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ with optional
    stripeSubscriptionId and status (admin override) fields.
    Equivalent of createMembershipApi in utils/api.ts.

    Paramètres / Parameters:
    - valid_until            : ISO date string (deadline de l'adhésion)
    - override_status        : code statut (ex: 'A' pour ONCE)
    - stripe_subscription_id : identifiant Stripe sub (ex: 'sub_test_00000000')
    """
    additional_property = [
        {
            "@type": "PropertyValue",
            "name": "paymentMode",
            "value": payment_mode,
        }
    ]
    if override_status is not None:
        additional_property.append(
            {
                "@type": "PropertyValue",
                "name": "status",
                "value": override_status,
            }
        )
    if stripe_subscription_id is not None:
        additional_property.append(
            {
                "@type": "PropertyValue",
                "name": "stripeSubscriptionId",
                "value": stripe_subscription_id,
            }
        )

    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": first_name,
            "familyName": last_name,
        },
        "membershipPlan": {
            "@type": "Offer",
            "identifier": price_uuid,
        },
        "additionalProperty": additional_property,
    }

    if valid_until is not None:
        payload["validUntil"] = valid_until

    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/memberships/",
        headers=_api_headers(api_key),
        json=payload,
        verify=False,
        timeout=30,
    )
    data = None
    try:
        data = resp.json()
    except ValueError:
        pass
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "data": data,
        "text": resp.text[:500],
    }


class TestMembershipRecurringCancel:
    """Annulation d'un prélèvement automatique — bouton visible et erreur attendue.
    / Cancellation of automatic debit — button visible and error expected.
    """

    def test_cancel_button_visible_and_shows_error(
        self, page, login_as, create_product, api_key, django_shell
    ):
        """Crée une adhésion récurrente AUTO, vérifie le bouton annulation et
        que le clic affiche un message d'erreur (sub Stripe fictif).
        / Creates a recurring AUTO membership, verifies the cancel button and
        that clicking it shows an error message (fake Stripe sub).
        """
        random_id = _random_id()
        user_email = f"jturbeaux+auto{random_id}@pm.me"
        product_name = f"Adhesion Auto {random_id}"
        price_name = "Mensuelle"

        # --- Étape 1 : Créer le produit d'adhésion récurrente mensuel via API ---
        # subscriptionType 'M' = mensuel, recurringPayment=True
        # / Step 1: Create recurring monthly membership product via API
        # subscriptionType 'M' = monthly, recurringPayment=True
        product_result = create_product(
            name=product_name,
            description="Produit adhesion recurrente.",
            category="Membership",
            offers=[
                {
                    "name": price_name,
                    "price": "10.00",
                    "recurringPayment": True,
                    "subscriptionType": "M",
                }
            ],
        )
        assert product_result["ok"], (
            f"Création du produit récurrent échouée : {product_result}"
        )

        # Récupérer l'UUID du tarif par son nom dans les offres retournées.
        # La création d'un produit Membership peut créer un tarif gratuit auto
        # (signal post_save) — on filtre donc par nom.
        # / Get price UUID by name from returned offers.
        # Membership product creation may auto-create a free price (post_save signal)
        # — so we filter by name.
        offers = product_result.get("offers") or []
        price_uuid = ""
        for offer in offers:
            if offer.get("name") == price_name:
                price_uuid = offer.get("identifier") or ""
                break
        assert price_uuid, (
            f"UUID du tarif '{price_name}' introuvable dans les offres : {offers}"
        )

        # --- Étape 2 : Créer l'adhésion AUTO via API ---
        # paymentMode FREE → last_contribution est défini, adhésion active (ONCE)
        # status='A' : override vers ONCE (Payé en ligne) — la condition du
        # bouton annulation dans le template est : status == 'A'.
        # stripeSubscriptionId simulé pour déclencher l'affichage du bouton.
        # validUntil = maintenant + 30 jours (adhésion valide, pas expirée).
        # / Step 2: Create AUTO membership via API
        # paymentMode FREE → last_contribution set, membership active (ONCE)
        # status='A': override to ONCE — template cancel button condition: status == 'A'.
        # Simulated stripeSubscriptionId to trigger button display.
        # validUntil = now + 30 days (valid, not expired).
        valid_until = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=30)
        ).isoformat()

        membership_result = _create_membership_api_with_sub(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email,
            first_name="Auto",
            last_name="Test",
            payment_mode="FREE",
            valid_until=valid_until,
            override_status="A",
            stripe_subscription_id="sub_test_00000000",
        )
        assert membership_result["ok"], (
            f"Création de l'adhésion AUTO échouée : {membership_result}"
        )

        # --- Étape 3 : Activer le compte utilisateur créé par l'API ---
        # L'API adhésion crée l'utilisateur avec is_active=False (email non validé).
        # ModelBackend.get_user refuse les users inactifs : la session force_login
        # serait anonyme et la vue /my_account/membership/ redirigerait vers le
        # formulaire de connexion.
        # On active le user en DB via django_shell (équivalent du lien TEST MODE
        # que le spec TypeScript utilisait pour valider l'email).
        # / Step 3: Activate the user account created by the API
        # The membership API creates the user with is_active=False (email not
        # validated). ModelBackend.get_user rejects inactive users: the
        # force_login session would be anonymous and /my_account/membership/ would
        # redirect to the login form. We activate the user in DB via django_shell
        # (equivalent of the TEST MODE magic link used in the TypeScript spec).
        activation_output = django_shell(
            "from AuthBillet.models import TibilletUser; "
            f"TibilletUser.objects.filter(email='{user_email}')"
            ".update(is_active=True, email_valid=True); "
            "print('USER_ACTIVE_OK')"
        )
        assert "USER_ACTIVE_OK" in activation_output, (
            f"Activation utilisateur échouée : {activation_output}"
        )

        login_as(page, user_email)

        # --- Étape 4 : Naviguer vers la page des adhésions du compte ---
        # /my_account/membership/ → liste les adhésions actives de l'utilisateur.
        # / Step 4: Navigate to the account membership page
        # /my_account/membership/ → lists the user's active memberships.
        page.goto("/my_account/membership/")
        page.wait_for_load_state("domcontentloaded")

        # --- Étape 5 : Vérifier que le bouton "Annuler le prélèvement" est visible ---
        # Le bouton a un data-testid "membership-cancel-auto-<uuid>".
        # Il s'affiche quand : status=='A' ET stripe_id_subscription ET pas d'engagement.
        # / Step 5: Verify that the "Cancel automatic debit" button is visible
        # Button has data-testid "membership-cancel-auto-<uuid>".
        # Shown when: status=='A' AND stripe_id_subscription AND no commitment.
        cancel_button = page.locator('[data-testid^="membership-cancel-auto-"]').first
        expect(cancel_button).to_be_visible(timeout=10_000)

        # --- Étape 6 : Cliquer sur le bouton d'annulation ---
        # Le formulaire envoie une requête HTMX POST à /api/cancel_sub/ avec
        # le UUID de l'adhésion. Le sub Stripe 'sub_test_00000000' est fictif,
        # donc Stripe retourne une erreur → le template affiche .alert-danger.
        # / Step 6: Click the cancel button
        # The form sends an HTMX POST to /api/cancel_sub/ with the membership UUID.
        # The Stripe sub 'sub_test_00000000' is fake, so Stripe returns an error
        # → the template renders .alert-danger.
        cancel_button.click()

        # Attendre que la réponse HTMX remplace le contenu.
        # / Wait for the HTMX response to replace the content.
        error_alert = page.locator(".alert-danger, .alert-warning").first
        expect(error_alert).to_be_visible(timeout=15_000)
