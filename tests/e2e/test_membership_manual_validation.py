"""
Tests E2E : validation manuelle d'adhésion par l'admin.
/ E2E tests: manual membership validation by admin.

Conversion de tests/playwright/tests/14-membership-manual-validation.spec.ts

Scénario unique :
1. Créer un produit adhésion avec un tarif à validation manuelle (manualValidation=true)
2. L'utilisateur soumet une demande d'adhésion via /memberships/
3. L'admin valide via l'endpoint /memberships/<uuid>/admin_accept/
4. Vérifier en base que le statut passe de AW (ADMIN_WAITING) à AV (ADMIN_VALID)

/ Single scenario:
1. Create a membership product with a manually-validated price (manualValidation=true)
2. User submits a membership request via /memberships/
3. Admin validates via /memberships/<uuid>/admin_accept/
4. Verify in DB that status transitions from AW (ADMIN_WAITING) to AV (ADMIN_VALID)
"""

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
# Même logique que conftest.py : depuis le container, on passe par le Docker
# gateway (Traefik) avec un header Host ; depuis l'hôte, URL directe.
# / Same logic as conftest.py: from container, go through Docker gateway
# (Traefik) with Host header; from host, direct URL.
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


class TestMembershipManualValidation:
    """Validation manuelle d'adhésion par l'admin.
    / Manual membership validation by admin.
    """

    def test_request_and_approve_membership(
        self, page, create_product, login_as_admin, django_shell
    ):
        """L'utilisateur demande une adhésion à validation manuelle, l'admin approuve.
        Vérifie que le statut passe à AV (ADMIN_VALID).
        / User requests a manually-validated membership, admin approves it.
        Verifies that status transitions to AV (ADMIN_VALID).
        """
        random_id = _random_id()
        product_name = f"Adhesion Validation Selective {random_id}"
        user_email = f"jturbeaux+val{random_id}@pm.me"

        # --- Étape 0 : Créer le produit adhésion avec tarif à validation manuelle ---
        # Le tarif "Solidaire" a manualValidation=True, "Plein tarif" n'en a pas.
        # / Step 0: Create membership product with manually-validated price.
        # "Solidaire" price has manualValidation=True, "Plein tarif" does not.
        product_result = create_product(
            name=product_name,
            description="Tarif solidaire soumis a validation manuelle",
            category="Membership",
            offers=[
                {
                    "name": "Solidaire",
                    "price": "2.00",
                    "subscriptionType": "Y",
                    "manualValidation": True,
                },
                {
                    "name": "Plein tarif",
                    "price": "30.00",
                    "subscriptionType": "Y",
                },
            ],
        )
        assert product_result["ok"], (
            f"Création du produit adhésion échouée : {product_result}"
        )
        product_uuid = product_result.get("uuid")
        assert product_uuid, f"UUID produit manquant : {product_result}"

        # Récupérer l'UUID du tarif "Solidaire" dans les offres retournées.
        # Signal post_save peut créer un "Tarif gratuit" auto — filtrer par nom.
        # / Get the UUID of the "Solidaire" price from the returned offers.
        # post_save signal may auto-create a "Tarif gratuit" — filter by name.
        offers = product_result.get("offers") or []
        solidaire_price_uuid = ""
        for offer in offers:
            if offer.get("name") == "Solidaire":
                solidaire_price_uuid = offer.get("identifier") or ""
                break
        assert solidaire_price_uuid, (
            f"UUID du tarif Solidaire introuvable dans les offres : {offers}"
        )

        # --- Étape 1 : L'utilisateur soumet une demande d'adhésion ---
        # Via /memberships/ : ouvrir l'offcanvas, remplir le formulaire,
        # sélectionner le tarif "Solidaire" (à validation manuelle), soumettre.
        # Avec manualValidation=True, le statut passe à AW (ADMIN_WAITING)
        # sans redirection vers Stripe.
        # / Step 1: User submits a membership request.
        # Via /memberships/: open offcanvas, fill form, select "Solidaire" price
        # (manually validated), submit.
        # With manualValidation=True, status becomes AW (ADMIN_WAITING)
        # without Stripe redirect.
        page.goto("/memberships/")
        page.wait_for_load_state("domcontentloaded")

        # Trouver la carte du produit et cliquer sur le bouton "Adhérer" / "Subscribe".
        # / Find the product card and click the "Adhérer" / "Subscribe" button.
        card = page.locator(f'.card:has-text("{product_name}")').first
        card.locator(
            'button:has-text("Subscribe"), button:has-text("Adhérer")'
        ).click()

        # Attendre que l'offcanvas soit visible.
        # / Wait for the offcanvas to be visible.
        page.wait_for_selector("#subscribePanel.show", state="visible", timeout=10_000)

        # Remplir le formulaire dans l'offcanvas.
        # / Fill the form in the offcanvas.
        page.locator('#subscribePanel input[name="email"]').fill(user_email)
        page.locator('#subscribePanel input[name="confirm-email"]').fill(user_email)
        page.locator('#subscribePanel input[name="firstname"]').fill("Candidate")
        page.locator('#subscribePanel input[name="lastname"]').fill("User")

        # Sélectionner le tarif "Solidaire" (validation manuelle).
        # Le label contient "Solidaire" — clic sur le label sélectionne le radio.
        # / Select the "Solidaire" price (manual validation).
        # The label contains "Solidaire" — clicking the label selects the radio.
        price_label = page.locator('label:has-text("Solidaire")').first
        price_label.click()

        # Soumettre le formulaire.
        # / Submit the form.
        page.locator("#membership-submit").click()

        # Avec manualValidation=True, la soumission devrait afficher un message
        # de confirmation (pas de redirection Stripe immédiate).
        # On attend soit un message "en attente" soit un retour sur /memberships/.
        # / With manualValidation=True, submission should show a confirmation message
        # (no immediate Stripe redirect).
        # We wait for either a "pending" message or return to /memberships/.
        try:
            page.wait_for_url(
                lambda url: "checkout.stripe.com" in url,
                timeout=8_000,
            )
            # Si Stripe apparaît (comportement inattendu mais possible), on note
            # et on continue — le statut AW peut être créé avant la redirection.
            # / If Stripe appears (unexpected but possible), note it and continue —
            # AW status may be created before the redirect.
        except Exception:
            # Pas de redirection Stripe — comportement attendu pour manualValidation.
            # / No Stripe redirect — expected behavior for manualValidation.
            pass

        # --- Étape 2 : Vérifier en base que l'adhésion est en statut AW ---
        # Récupérer l'UUID de l'adhésion en base via django_shell.
        # Code shell avec quotes simples uniquement (conftest échappe les doubles).
        # / Step 2: Verify in DB that the membership is in AW status.
        # Get the membership UUID from DB via django_shell.
        # Shell code uses single quotes only (conftest escapes double quotes).
        result_pre = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{user_email}').order_by('-pk').first()\n"
            "if m:\n"
            "    print(f'uuid={m.uuid}')\n"
            "    print(f'status={m.status}')\n"
            "else:\n"
            "    print('NOT_FOUND')"
        )

        assert "NOT_FOUND" not in result_pre, (
            f"Adhésion introuvable pour {user_email}. Shell: {result_pre}"
        )

        uuid_match = re.search(r"uuid=([a-f0-9-]+)", result_pre)
        assert uuid_match is not None, f"UUID non trouvé dans : {result_pre}"
        membership_uuid = uuid_match.group(1)

        status_match = re.search(r"status=(\w+)", result_pre)
        pre_status = status_match.group(1) if status_match else "unknown"

        # Le statut devrait être AW (ADMIN_WAITING) après soumission manualValidation.
        # / Status should be AW (ADMIN_WAITING) after manualValidation submission.
        assert pre_status == "AW", (
            f"Statut attendu AW (ADMIN_WAITING) avant validation, obtenu : '{pre_status}'. "
            f"Shell: {result_pre}"
        )

        # --- Étape 3 : L'admin valide l'adhésion via l'endpoint admin_accept ---
        # L'endpoint /memberships/<uuid>/admin_accept/ accepte POST avec HX-Request.
        # Nécessite un cookie de session admin + CSRF token.
        # / Step 3: Admin validates the membership via admin_accept endpoint.
        # The /memberships/<uuid>/admin_accept/ endpoint accepts POST with HX-Request.
        # Requires admin session cookie + CSRF token.
        login_as_admin(page)

        # Naviguer sur le site pour obtenir le cookie CSRF.
        # / Navigate to the site to get the CSRF cookie.
        page.goto("/admin/")
        page.wait_for_load_state("domcontentloaded")

        # Récupérer le token CSRF depuis les cookies du contexte Playwright.
        # / Get the CSRF token from Playwright context cookies.
        cookies = page.context.cookies()
        csrf_token = ""
        for cookie in cookies:
            if cookie["name"] == "csrftoken":
                csrf_token = cookie["value"]
                break

        assert csrf_token, (
            "Token CSRF introuvable dans les cookies. "
            "L'admin doit être connecté et le site doit avoir défini le cookie csrftoken."
        )

        # Appeler l'endpoint admin_accept via une requête POST depuis Playwright.
        # L'endpoint gère : AW → AV + envoi email, ou AV → envoi email seulement.
        # / Call the admin_accept endpoint via a POST request from Playwright.
        # The endpoint handles: AW → AV + email, or AV → email only.
        accept_response = page.request.post(
            f"/memberships/{membership_uuid}/admin_accept/",
            headers={
                "HX-Request": "true",
                "X-CSRFToken": csrf_token,
                "Referer": f"https://{SUB}.{DOMAIN}/admin/",
            },
        )
        assert accept_response.ok, (
            f"Endpoint admin_accept a échoué : HTTP {accept_response.status}. "
            f"Body: {accept_response.text()[:300]}"
        )

        # --- Étape 4 : Vérifier en base que le statut est AV (ADMIN_VALID) ---
        # La validation manuelle met le statut ADMIN_VALID (AV) ;
        # le paiement par l'utilisateur viendra ensuite via le lien envoyé par email.
        # / Step 4: Verify in DB that status is AV (ADMIN_VALID).
        # Manual validation sets ADMIN_VALID (AV) status;
        # user payment will come later via the link sent by email.
        result_post = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{user_email}').order_by('-pk').first()\n"
            "if m:\n"
            "    print(f'status={m.status}')\n"
            "else:\n"
            "    print('NOT_FOUND')"
        )

        assert "NOT_FOUND" not in result_post, (
            f"Adhésion introuvable après validation pour {user_email}. Shell: {result_post}"
        )

        post_status_match = re.search(r"status=(\w+)", result_post)
        assert post_status_match is not None, (
            f"Statut non trouvé dans : {result_post}"
        )
        post_status = post_status_match.group(1)

        # Assertion principale : le statut doit être AV (ADMIN_VALID).
        # / Main assertion: status must be AV (ADMIN_VALID).
        assert post_status == "AV", (
            f"Statut attendu AV (ADMIN_VALID) après validation admin, obtenu : '{post_status}'. "
            f"Shell: {result_post}"
        )
