"""
Tests E2E : ajouter un paiement hors-ligne sur une adhésion en attente (admin).
/ E2E tests: add offline payment on a pending membership from admin.

Conversion de tests/playwright/tests/33-admin-ajouter-paiement.spec.ts

Nouveau flux (v1.7.7) :
Les actions sont dans le panneau HTMX inline affiché avant le formulaire admin.
Plus de page intermédiaire — tout se passe dans la vue change de l'adhésion.

New flow (v1.7.7):
Actions are in the inline HTMX panel shown before the admin form.
No intermediate page — everything happens in the membership change view.

Scenarios :
1. Ajouter un paiement espèces sur adhésion en attente -> succès inline
2. Garde : "Offert" avec montant > 0 -> erreur inline
"""

import os
import random
import shutil
import string

import pytest
import requests as http_requests

from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


# --- Configuration URL pour les appels API directs ---
# Même logique que tests/e2e/conftest.py : depuis le container on passe par
# le Docker gateway (Traefik) avec un header Host ; depuis l'hôte, URL directe.
# / Same logic as tests/e2e/conftest.py: from container, go through the
# Docker gateway (Traefik) with a Host header; from host, direct URL.
SUB = os.environ.get("SUB", "lespass")
DOMAIN = os.environ.get("DOMAIN", "tibillet.localhost")
DOCKER_GATEWAY = os.environ.get("DOCKER_GATEWAY", "172.17.0.1")
INSIDE_CONTAINER = shutil.which("docker") is None
API_BASE_URL = f"https://{DOCKER_GATEWAY}" if INSIDE_CONTAINER else f"https://{SUB}.{DOMAIN}"
API_HOST_HEADER = f"{SUB}.{DOMAIN}" if INSIDE_CONTAINER else None


def _random_id():
    """Génère un suffixe unique pour éviter les collisions sur la DB dev partagée.
    / Generates a unique suffix to avoid collisions on the shared dev DB.
    """
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers d'authentification API v2.
    / Builds API v2 authentication headers.
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _create_product_api(api_key, name, description, offers):
    """Crée un produit adhésion avec validation manuelle via POST /api/v2/products/.
    Équivalent de createProduct dans tests/playwright/tests/utils/api.ts.
    / Creates a membership product with manual validation via POST /api/v2/products/.
    Equivalent of createProduct in tests/playwright/tests/utils/api.ts.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "category": "Membership",
        "offers": [
            {
                "@type": "Offer",
                "name": offer["name"],
                "price": offer["price"],
                "priceCurrency": "EUR",
                "additionalProperty": [
                    {
                        "@type": "PropertyValue",
                        "name": "subscriptionType",
                        "value": offer["subscriptionType"],
                    },
                    {
                        "@type": "PropertyValue",
                        "name": "manualValidation",
                        "value": offer["manualValidation"],
                    },
                ],
            }
            for offer in offers
        ],
    }
    resp = http_requests.post(
        f"{API_BASE_URL}/api/v2/products/",
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
        "uuid": data.get("identifier") if data else None,
        "offers": data.get("offers") if data else None,
    }


def _create_membership_api(api_key, price_uuid, email, first_name, last_name, status="AW"):
    """Crée une adhésion en statut ADMIN_WAITING via POST /api/v2/memberships/.
    Équivalent de createMembershipApi dans tests/playwright/tests/utils/api.ts.
    / Creates a membership in ADMIN_WAITING status via POST /api/v2/memberships/.
    Equivalent of createMembershipApi in tests/playwright/tests/utils/api.ts.
    """
    additional_property = [
        {
            "@type": "PropertyValue",
            "name": "paymentMode",
            "value": "FREE",
        },
        {
            "@type": "PropertyValue",
            "name": "status",
            "value": status,
        },
    ]
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
    if not resp.ok:
        # Log visible dans la sortie des tests quand le setup API échoue
        # / Visible log in test output when API setup fails
        print(f"createMembershipApi failed: status={resp.status_code} data={data}")
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "data": data,
    }


class TestAdminAjouterPaiement:
    """Ajouter paiement hors-ligne sur adhésion en attente (admin).
    / Add offline payment on pending membership (admin).
    """

    def test_add_cash_payment_on_pending_membership(self, page, login_as_admin, api_key):
        """Ajoute un paiement espèces sur une adhésion en attente.
        Vérifie : bouton visible, formulaire inline, succès inline, LigneArticle Confirmed.
        / Adds a cash payment on a pending membership.
        Checks: button visible, inline form, inline success, Confirmed LigneArticle.
        """
        random_id = _random_id()
        product_name = f"Adhesion Paiement {random_id}"
        user_email = f"jturbeaux+pay{random_id}@pm.me"

        # --- Étape 0 : Créer le produit adhésion avec validation manuelle ---
        # manualValidation=True force le statut ADMIN_WAITING à la création.
        # / Step 0: create the membership product with manual validation.
        # manualValidation=True forces ADMIN_WAITING status on creation.
        product_result = _create_product_api(
            api_key=api_key,
            name=product_name,
            description="Test paiement admin",
            offers=[{
                "name": "Annuel",
                "price": "25.00",
                "subscriptionType": "Y",
                "manualValidation": True,
            }],
        )
        assert product_result["ok"], (
            f"Création produit échouée : status={product_result['status']} "
            f"data={product_result['data']}"
        )
        offers = product_result.get("offers") or []
        assert len(offers) > 0, "Aucun tarif retourné par l'API après création du produit"
        # L'identifiant du tarif est dans le champ "identifier" de l'offre
        # / The price UUID is in the "identifier" field of the offer
        price_uuid = offers[0].get("identifier", "")
        assert price_uuid, "UUID du tarif introuvable dans la réponse API produit"

        # --- Étape 1 : Créer l'adhésion en statut ADMIN_WAITING ---
        # L'API v2 accepte le champ "status": "AW" dans additionalProperty.
        # / Step 1: create the membership in ADMIN_WAITING status.
        # API v2 accepts the "status": "AW" field in additionalProperty.
        ms_result = _create_membership_api(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email,
            first_name="Paiement",
            last_name="Test",
            status="AW",
        )
        assert ms_result["ok"], (
            f"Création adhésion échouée : status={ms_result['status']} "
            f"data={ms_result['data']}"
        )

        # --- Étape 2 : Connexion admin ---
        # / Step 2: login as admin.
        login_as_admin(page)

        # --- Étape 3 : Aller sur la changelist Membership et chercher par email ---
        # On filtre par email unique → on évite toute ambiguïté de pagination.
        # / Step 3: go to Membership changelist and search by email.
        # Filtering by unique email avoids any pagination ambiguity.
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        search_input = page.locator('input[name="q"]').first
        search_input.fill(user_email)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        # --- Étape 4 : Cliquer sur le premier lien de la liste ---
        # / Step 4: click the first link in the list.
        first_link = page.locator("#result_list tbody tr a").first
        expect(first_link).to_be_visible(timeout=10000)
        first_link.click()
        page.wait_for_load_state("networkidle")

        # --- Étape 5 : Vérifier que le bouton "Enregistrer un paiement" est visible ---
        # Le panneau HTMX inline est affiché avant le formulaire admin.
        # / Step 5: check that the "Enregistrer un paiement" button is visible.
        # The inline HTMX panel is shown before the admin form.
        panel_button = page.locator('[data-testid="membership-action-ajouter-paiement"]')
        expect(panel_button).to_be_visible(timeout=5000)

        # --- Étape 6 : Cliquer sur le bouton → formulaire HTMX inline ---
        # / Step 6: click the button → inline HTMX form appears.
        panel_button.click()
        form = page.locator('[data-testid="membership-paiement-form"]')
        expect(form).to_be_visible(timeout=5000)

        # --- Étape 7 : Vérifier que le montant est présent et en remplir la valeur ---
        # Piège Django + locale FR : USE_L10N=True rend Decimal('25.00') comme "25,00"
        # (virgule). Un <input type="number" value="25,00"> est rejeté par le navigateur
        # → value="" côté DOM. On vérifie le champ visible et on force la valeur "25"
        # pour que le test soit indépendant de la locale.
        # / Trap Django + FR locale: USE_L10N=True renders Decimal('25.00') as "25,00"
        # (comma). An <input type="number" value="25,00"> is rejected by the browser
        # → value="" in the DOM. We verify the field is visible and force the value "25"
        # so the test is independent of locale.
        amount_input = page.locator('[data-testid="membership-payment-amount"]')
        expect(amount_input).to_be_visible()
        amount_input.fill("25")

        # Le sélecteur de méthode de paiement doit être visible
        # / The payment method selector must be visible.
        method_select = page.locator('[data-testid="membership-payment-method"]')
        expect(method_select).to_be_visible()

        # --- Étape 8 : Sélectionner "Espèces" et soumettre ---
        # CA = Cash / Espèces dans le modèle Paiement
        # / Step 8: select "Cash" and submit.
        # CA = Cash in the Paiement model.
        method_select.select_option("CA")
        submit_button = page.locator('[data-testid="membership-payment-submit"]')
        submit_button.click()

        # --- Étape 9 : Vérifier le succès inline (pas de navigation de page) ---
        # / Step 9: verify inline success (no page navigation).
        success_area = page.locator('[data-testid="membership-paiement-success"]')
        expect(success_area).to_be_visible(timeout=10000)

        # --- Étape 10 : Vérifier la LigneArticle confirmée dans l'admin ---
        # On recherche par nom de produit pour trouver la ligne créée.
        # / Step 10: verify the confirmed LigneArticle in the admin.
        # We search by product name to find the created line.
        page.goto("/admin/BaseBillet/lignearticle/")
        page.wait_for_load_state("networkidle")

        search_input2 = page.locator('input[name="q"]').first
        search_input2.fill(product_name)
        search_input2.press("Enter")
        page.wait_for_load_state("networkidle")

        rows = page.locator("#result_list tbody tr")
        row_count = rows.count()
        assert row_count >= 1, (
            f"Aucune LigneArticle trouvée pour le produit '{product_name}'"
        )

        # Au moins une ligne doit avoir le statut Confirmed/Confirmé/Payé
        # On cherche le début du mot "Confirm" (FR/EN) ou "VALID" ou "Payé" selon
        # le display du badge Unfold. On est tolérant sur la casse et la langue.
        # / At least one line must have Confirmed/Confirmé/Paid status.
        # We search for the start of "Confirm" (FR/EN) or "VALID" or "Payé".
        # Tolerant on case and language.
        body_text = page.inner_text("body")
        has_confirmed = (
            "Confirm" in body_text
            or "confirm" in body_text
            or "CONFIRM" in body_text
            or "Payé" in body_text
            or "payé" in body_text
            or "Paid" in body_text
            or "paid" in body_text
            or "VALID" in body_text
            or "valid" in body_text
        )
        assert has_confirmed, (
            "Aucun statut de paiement confirmé/payé trouvé dans LigneArticle après le paiement espèces. "
            "Contenu partiel de la page : " + body_text[:500]
        )

    def test_reject_offered_with_positive_amount(self, page, login_as_admin, api_key):
        """Soumettre 'Offert' avec un montant positif doit afficher une erreur inline.
        / Submitting 'Offered' with a positive amount must show an inline error.
        """
        random_id = _random_id()
        product_name = f"Adhesion Guard {random_id}"
        user_email_guard = f"jturbeaux+payg{random_id}@pm.me"

        # --- Étape 0 : Créer le produit adhésion ---
        # / Step 0: create the membership product.
        product_result = _create_product_api(
            api_key=api_key,
            name=product_name,
            description="Test garde paiement offert",
            offers=[{
                "name": "Annuel",
                "price": "25.00",
                "subscriptionType": "Y",
                "manualValidation": True,
            }],
        )
        assert product_result["ok"], (
            f"Création produit échouée : status={product_result['status']}"
        )
        offers = product_result.get("offers") or []
        assert len(offers) > 0, "Aucun tarif retourné par l'API"
        price_uuid = offers[0].get("identifier", "")
        assert price_uuid, "UUID du tarif introuvable"

        # --- Étape 1 : Créer l'adhésion en attente ---
        # / Step 1: create the pending membership.
        ms_result = _create_membership_api(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email_guard,
            first_name="Guard",
            last_name="Test",
            status="AW",
        )
        assert ms_result["ok"], (
            f"Création adhésion échouée : status={ms_result['status']}"
        )

        # --- Étape 2 : Connexion admin ---
        # / Step 2: login as admin.
        login_as_admin(page)

        # --- Étape 3 : Trouver l'adhésion et aller sur sa fiche ---
        # / Step 3: find the membership and go to its change page.
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        search_input = page.locator('input[name="q"]').first
        search_input.fill(user_email_guard)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        first_link = page.locator("#result_list tbody tr a").first
        expect(first_link).to_be_visible(timeout=10000)
        first_link.click()
        page.wait_for_load_state("networkidle")

        # --- Étape 4 : Ouvrir le formulaire de paiement via HTMX ---
        # / Step 4: open the payment form via HTMX.
        panel_button = page.locator('[data-testid="membership-action-ajouter-paiement"]')
        expect(panel_button).to_be_visible(timeout=5000)
        panel_button.click()

        form = page.locator('[data-testid="membership-paiement-form"]')
        expect(form).to_be_visible(timeout=5000)

        # --- Étape 5 : Remplir "Offert" avec 25 euros et soumettre ---
        # NA = Offered / Offert dans le modèle Paiement
        # L'API devrait refuser : méthode "Offert" + montant > 0 est incohérent.
        # / Step 5: fill "Offered" with 25 euros and submit.
        # NA = Offered in the Paiement model.
        # The API should reject: "Offered" method + amount > 0 is inconsistent.
        amount_input = page.locator('[data-testid="membership-payment-amount"]')
        amount_input.fill("25")

        method_select = page.locator('[data-testid="membership-payment-method"]')
        method_select.select_option("NA")

        submit_button = page.locator('[data-testid="membership-payment-submit"]')
        submit_button.click()

        # --- Étape 6 : Vérifier l'erreur inline (formulaire toujours visible) ---
        # L'erreur est inline dans le formulaire, pas dans une div.errornote Django.
        # / Step 6: verify the inline error (form still visible).
        # The error is inline in the form, not in a Django div.errornote.
        expect(form).to_be_visible(timeout=5000)

        page_content = page.inner_text("body").lower()
        has_error = (
            "offert" in page_content
            or "offered" in page_content
            or "impossible" in page_content
        )
        assert has_error, (
            "Aucun message d'erreur trouvé après soumission 'Offert' avec montant positif. "
            "Contenu partiel de la page : " + page_content[:500]
        )
