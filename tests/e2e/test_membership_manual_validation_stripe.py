"""
Tests E2E : adhésion à validation manuelle avec paiement Stripe via lien copié.
/ E2E tests: manual validation membership with Stripe payment via copied link.

Conversion de tests/playwright/tests/43-membership-manual-validation-stripe-payment.spec.ts

Flux complet couvert :
1. Création d'un produit adhésion avec validation manuelle (API v2)
2. Création d'une adhésion en attente via API (statut AW)
3. Récupération de l'UUID de l'adhésion en base (django_shell)
4. Validation admin via l'endpoint /memberships/<uuid>/admin_accept/ (AW → AV)
5. Vérification du bouton "Copier le lien" dans le panneau admin
6. Paiement Stripe via le lien /memberships/<uuid>/get_checkout_for_membership
7. Vérification que le statut passe à A (ONCE = payé en ligne) après le webhook
8. Vérification dans la liste admin : statut, deadline, contribution, booléen valid
9. Vérification dans les Ventes (LigneArticle confirmée)

/ Full flow covered:
1. Create membership product with manual validation (API v2)
2. Create pending membership via API (status AW)
3. Get membership UUID from DB (django_shell)
4. Admin validation via /memberships/<uuid>/admin_accept/ endpoint (AW → AV)
5. Verify "Copy link" button in admin panel
6. Stripe payment via /memberships/<uuid>/get_checkout_for_membership link
7. Verify status transitions to A (ONCE = paid online) after webhook
8. Verify in admin list: status, deadline, contribution, valid boolean
9. Verify in Sales (confirmed LigneArticle)
"""

import os
import random
import re
import shutil
import string
import time

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


def _create_membership_api_with_status(
    api_key,
    price_uuid,
    email,
    first_name="Stripe",
    last_name="Validation",
    status="AW",
):
    """Crée une adhésion via POST /api/v2/memberships/ avec un statut initial.
    Équivalent de createMembershipApi({ status: 'AW' }) dans utils/api.ts.
    / Creates a membership via POST /api/v2/memberships/ with an initial status.
    Equivalent of createMembershipApi({ status: 'AW' }) in utils/api.ts.
    """
    additional_property = [
        {
            "@type": "PropertyValue",
            "name": "status",
            "value": status,
        }
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
    return {
        "ok": resp.ok,
        "status": resp.status_code,
        "data": data,
        "text": resp.text[:500],
    }


def _rechercher_dans_liste_admin(page, email):
    """Cherche une adhésion dans la liste admin par email et retourne la ligne.
    Précondition : page est déjà sur /admin/BaseBillet/membership/
    / Searches for a membership in the admin list by email and returns the row.
    Precondition: page is already on /admin/BaseBillet/membership/
    """
    # Recherche via l'input q de la changelist Django admin.
    # / Search via the Django admin changelist q input.
    search_input = page.locator('input[name="q"]').first
    search_input.fill(email)
    search_input.press("Enter")
    page.wait_for_load_state("networkidle")
    return page.locator("#result_list tbody tr").filter(has_text=email)


# Ce parcours ne s'acheve qu'au retour du webhook Stripe : l'adhesion ne passe
# au statut paye que lorsque Stripe rappelle. Sans `stripe listen`, l'attente en
# base tourne dans le vide et le test echoue au bout de ses 15 tentatives, pour
# une raison qui n'a rien a voir avec le code.
# / This journey only completes when the Stripe webhook returns. Without
# `stripe listen` the DB polling spins for nothing and fails after 15 attempts.
@pytest.mark.stripe_listen
class TestMembershipManualValidationStripe:
    """Adhésion à validation manuelle + paiement Stripe via lien copié.
    / Manual validation membership + Stripe payment via copied link.
    """

    def test_flux_complet_validation_manuelle_stripe(
        self, page, create_product, login_as_admin, django_shell, fill_stripe_card,
        soumettre_paiement_stripe, api_key
    ):
        """Flux complet : créer → valider → copier lien → payer → vérifier.
        / Full flow: create → validate → copy link → pay → verify.
        """
        # Timeouts généreux pour Stripe (checkout.stripe.com peut être lent).
        # / Generous timeouts for Stripe (checkout.stripe.com can be slow).
        page.set_default_timeout(120_000)

        random_id = _random_id()
        product_name = f"Adhesion Validation Stripe {random_id}"
        price_name = f"Annuel Val {random_id}"
        user_email = f"jturbeaux+mv{random_id}@pm.me"

        # ──────────────────────────────────────────────────────────────────────
        # Étape 0 : Créer le produit adhésion avec validation manuelle (API v2)
        # Step 0: Create membership product with manual validation (API v2)
        # ──────────────────────────────────────────────────────────────────────
        product_result = create_product(
            name=product_name,
            description="Adhesion a validation manuelle pour test paiement Stripe",
            category="Membership",
            offers=[
                {
                    "name": price_name,
                    "price": "20.00",
                    "subscriptionType": "Y",
                    "manualValidation": True,
                }
            ],
        )
        assert product_result["ok"], (
            f"Création du produit adhésion échouée : {product_result}"
        )

        # Récupérer l'UUID du tarif créé via la liste des offres retournées.
        # Signal post_save peut créer un "Tarif gratuit" auto → filtrer par nom.
        # / Get the UUID of the created price from the returned offers list.
        # post_save signal may auto-create "Tarif gratuit" → filter by name.
        offers = product_result.get("offers") or []
        price_uuid = ""
        for offer in offers:
            if offer.get("name") == price_name:
                price_uuid = offer.get("identifier") or ""
                break
        # Fallback : prendre le premier tarif si la recherche par nom échoue.
        # / Fallback: take the first price if name lookup fails.
        if not price_uuid and offers:
            price_uuid = offers[0].get("identifier") or ""
        assert price_uuid, (
            f"UUID du tarif introuvable dans les offres retournées : {offers}"
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 1 : Créer l'adhésion en statut ADMIN_WAITING (AW) via API
        # Step 1: Create membership in ADMIN_WAITING (AW) status via API
        # ──────────────────────────────────────────────────────────────────────
        ms_result = _create_membership_api_with_status(
            api_key=api_key,
            price_uuid=price_uuid,
            email=user_email,
            first_name="Stripe",
            last_name="Validation",
            status="AW",
        )
        assert ms_result["ok"], (
            f"Création de l'adhésion AW via API échouée : {ms_result}"
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 2 : Récupérer l'UUID de l'adhésion en base via django_shell
        # Step 2: Get membership UUID from DB via django_shell
        # ──────────────────────────────────────────────────────────────────────
        # Code shell avec quotes simples uniquement (conftest échappe les doubles).
        # / Shell code uses single quotes only (conftest escapes double quotes).
        db_result = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{user_email}').order_by('-pk').first()\n"
            "if m:\n"
            "    print(f'uuid={m.uuid}')\n"
            "    print(f'status={m.status}')\n"
            "else:\n"
            "    print('NOT_FOUND')"
        )

        assert "NOT_FOUND" not in db_result, (
            f"Adhésion introuvable pour {user_email} après création API. "
            f"Shell: {db_result}"
        )

        uuid_match = re.search(r"uuid=([a-f0-9-]+)", db_result)
        assert uuid_match is not None, f"UUID non trouvé dans le résultat shell : {db_result}"
        membership_uuid = uuid_match.group(1)

        status_match = re.search(r"status=(\w+)", db_result)
        pre_status = status_match.group(1) if status_match else "unknown"
        assert pre_status == "AW", (
            f"Statut attendu AW (ADMIN_WAITING) après création, obtenu : '{pre_status}'. "
            f"Shell: {db_result}"
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 3 : L'admin valide l'adhésion (AW → AV) via endpoint admin_accept
        # Step 3: Admin validates membership (AW → AV) via admin_accept endpoint
        # ──────────────────────────────────────────────────────────────────────
        login_as_admin(page)

        # Naviguer sur le site pour que Playwright obtienne le cookie CSRF.
        # / Navigate to the site so Playwright gets the CSRF cookie.
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
        # L'endpoint gère : AW → AV + envoi email (validation manuelle).
        # / Call the admin_accept endpoint via a POST request from Playwright.
        # The endpoint handles: AW → AV + email send (manual validation).
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

        # Vérifier en base que le statut est passé à AV (ADMIN_VALID).
        # / Verify in DB that status changed to AV (ADMIN_VALID).
        db_after_accept = django_shell(
            "from BaseBillet.models import Membership\n"
            f"m = Membership.objects.filter(user__email='{user_email}').order_by('-pk').first()\n"
            "if m:\n"
            "    print(f'status={m.status}')\n"
            "else:\n"
            "    print('NOT_FOUND')"
        )
        status_av_match = re.search(r"status=(\w+)", db_after_accept)
        status_after_accept = status_av_match.group(1) if status_av_match else "unknown"
        assert status_after_accept == "AV", (
            f"Statut attendu AV (ADMIN_VALID) après validation admin, "
            f"obtenu : '{status_after_accept}'. Shell: {db_after_accept}"
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 4 : Vérifier le bouton "Copier le lien" dans la fiche admin
        # Step 4: Verify "Copy link" button in the admin change form
        # ──────────────────────────────────────────────────────────────────────
        # Aller sur la liste admin et chercher la fiche de l'adhésion.
        # / Go to admin list and find the membership change form.
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        row = _rechercher_dans_liste_admin(page, user_email)
        expect(row).to_be_visible(timeout=10_000)

        # Cliquer sur le premier lien de la ligne pour ouvrir la fiche.
        # / Click on the first link in the row to open the change form.
        first_link = row.locator("a").first
        first_link.click()
        page.wait_for_load_state("networkidle")

        # Le panneau d'actions doit contenir le bouton "Copier le lien".
        # Ce bouton est visible uniquement quand le statut est AV (ADMIN_VALID).
        # / The action panel must contain the "Copy link" button.
        # This button is visible only when status is AV (ADMIN_VALID).
        copy_button = page.locator('[data-testid="membership-action-copy-payment-link"]')
        expect(copy_button).to_be_visible(timeout=5_000)

        # Le bouton "Renvoyer le lien" (admin_accept de renvoi) doit aussi être visible.
        # / The "Resend link" button (resend admin_accept) must also be visible.
        resend_button = page.locator('[data-testid="membership-action-accept"]')
        expect(resend_button).to_be_visible(timeout=5_000)

        # ──────────────────────────────────────────────────────────────────────
        # Étape 5 : Payer via le lien de paiement (get_checkout_for_membership)
        # Step 5: Pay via payment link (get_checkout_for_membership)
        # ──────────────────────────────────────────────────────────────────────
        # Naviguer vers le lien de paiement (même URL que celle copiée par le bouton).
        # / Navigate to the payment link (same URL as copied by the button).
        payment_link = f"/memberships/{membership_uuid}/get_checkout_for_membership"
        page.goto(payment_link)

        # Attendre la redirection vers Stripe checkout.
        # Callback reçoit une STRING → utiliser 'in url' (pas regex sur objet URL).
        # / Wait for redirect to Stripe checkout.
        # Callback receives a STRING → use 'in url' (not regex on URL object).
        page.wait_for_url(
            lambda url: "checkout.stripe.com" in url,
            timeout=40_000,
        )

        # domcontentloaded au lieu de networkidle : Stripe maintient des connexions
        # persistantes (analytics, SSE) qui empêchent networkidle de se résoudre.
        # / domcontentloaded instead of networkidle: Stripe keeps persistent
        # connections that prevent networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")

        # Remplir le formulaire de paiement Stripe.
        # / Fill the Stripe payment form.
        fill_stripe_card(page, user_email)

        # Soumettre le paiement Stripe.
        # / Submit the Stripe payment.
        # Soumission robuste : un click() simple est parfois ignore par le
        # front Stripe, sans erreur ni requete (PIEGES 12.14).
        # / Robust submit: a plain click() is sometimes silently ignored.
        soumettre_paiement_stripe(page)

        # Attendre le retour vers le site (confirmation de paiement).
        # / Wait for return to the site (payment confirmation).
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url,
            timeout=60_000,
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 6 : Attendre le traitement du webhook Stripe puis vérifier en base
        # Step 6: Wait for Stripe webhook processing then verify DB status
        # ──────────────────────────────────────────────────────────────────────
        # Le webhook Stripe est asynchrone — on interroge la DB en boucle (15 tentatives max).
        # Statut cible : A (ONCE = payé en ligne).
        # / Stripe webhook is async — poll the DB in a loop (max 15 attempts).
        # Target status: A (ONCE = paid online).
        membership_status = ""
        for attempt in range(1, 16):
            db_paid = django_shell(
                "from BaseBillet.models import Membership\n"
                f"m = Membership.objects.filter(user__email='{user_email}').order_by('-pk').first()\n"
                "if m:\n"
                "    print(f'status={m.status}')\n"
                "else:\n"
                "    print('NOT_FOUND')"
            )
            status_paid_match = re.search(r"status=(\w+)", db_paid)
            membership_status = status_paid_match.group(1) if status_paid_match else ""

            if membership_status == "A":
                # Statut ONCE confirmé / ONCE status confirmed
                break

            if attempt < 15:
                # Attendre 2 secondes entre chaque tentative (webhook asynchrone).
                # / Wait 2 seconds between attempts (async webhook).
                time.sleep(2)

        assert membership_status == "A", (
            f"Statut attendu A (ONCE = payé en ligne) après paiement Stripe, "
            f"obtenu : '{membership_status}' après 15 tentatives."
        )

        # ──────────────────────────────────────────────────────────────────────
        # Étape 7 : Vérifier dans la liste admin : statut, deadline, contribution
        # Step 7: Verify in admin list: status, deadline, contribution
        # ──────────────────────────────────────────────────────────────────────
        # La session admin est toujours active après le retour de Stripe
        # (les cookies persistent dans le contexte Playwright).
        # / Admin session is still active after Stripe return
        # (cookies persist in Playwright context).
        page.goto("/admin/BaseBillet/membership/")
        page.wait_for_load_state("networkidle")

        row = _rechercher_dans_liste_admin(page, user_email)
        expect(row).to_be_visible(timeout=10_000)

        # Statut : "Payé en ligne" (status ONCE = 'A').
        # Tolérance FR/EN (langue variable selon config tenant).
        # / Status: "Payé en ligne" (ONCE = 'A').
        # FR/EN tolerance (language varies with tenant config).
        status_cell = row.locator("td.field-status")
        expect(status_cell).to_contain_text(
            re.compile(r"Pay[eé] en ligne|Paid online", re.IGNORECASE)
        )

        # Deadline : doit être une date au format JJ/MM/AAAA (pas "-").
        # L'adhésion annuelle calcule la deadline = last_contribution + 12 mois.
        # / Deadline: must be a date in DD/MM/YYYY format (not "-").
        # Annual membership calculates deadline = last_contribution + 12 months.
        deadline_cell = row.locator("td.field-display_deadline")
        deadline_text = deadline_cell.inner_text().strip()
        assert deadline_text != "-", (
            f"La deadline ne doit pas être '-', obtenu : '{deadline_text}'"
        )
        assert re.match(r"\d{2}/\d{2}/\d{4}", deadline_text), (
            f"La deadline doit être au format JJ/MM/AAAA, obtenu : '{deadline_text}'"
        )

        # Contribution : doit afficher 20 (le prix du tarif est 20.00 €).
        # / Contribution: must display 20 (the price amount is 20.00 €).
        contribution_cell = row.locator("td.field-contribution_value")
        contribution_text = contribution_cell.inner_text().strip()
        assert "20" in contribution_text, (
            f"La contribution doit contenir '20', obtenu : '{contribution_text}'"
        )

        # Booléen "valid" : doit être true (icône check verte ou équivalent).
        # / Boolean "valid": must be true (green check icon or equivalent).
        valid_cell = row.locator("td.field-display_is_valid")
        valid_element = valid_cell.locator('img[src*="icon-yes"], svg, span').first
        expect(valid_element).to_be_visible()

        # ──────────────────────────────────────────────────────────────────────
        # Étape 8 : Vérifier dans les Ventes (LigneArticle confirmée)
        # Step 8: Verify in Sales (confirmed LigneArticle)
        # ──────────────────────────────────────────────────────────────────────
        page.goto("/admin/BaseBillet/lignearticle/")
        page.wait_for_load_state("networkidle")

        # Chercher les lignes de vente liées à cet utilisateur.
        # / Search for sales lines linked to this user.
        search_input = page.locator('input[name="q"]').first
        search_input.fill(user_email)
        search_input.press("Enter")
        page.wait_for_load_state("networkidle")

        # Au moins une ligne de vente doit apparaître.
        # / At least one sales line must appear.
        rows = page.locator("#result_list tbody tr")
        row_count = rows.count()
        assert row_count >= 1, (
            f"Aucune LigneArticle trouvée pour {user_email} dans les Ventes."
        )

        # La page doit contenir un statut confirmé.
        # LigneArticle.VALID = 'V' → label FR "Confirmé" / EN "Paid and confirmed".
        # LigneArticle.PAID = 'P' → label FR "Payé" / EN "Paid".
        # / The page must contain a confirmed status.
        # LigneArticle.VALID = 'V' → FR "Confirmé" / EN "Paid and confirmed".
        # LigneArticle.PAID = 'P' → FR "Payé" / EN "Paid".
        body_text = page.locator("body").inner_text()
        has_valid_line = any(
            kw.lower() in body_text.lower()
            for kw in [
                "Confirmé",
                "confirmed",
                "Paid and confirmed",
                "Payé",
                "Paid",
            ]
        )
        assert has_valid_line, (
            f"Aucune LigneArticle confirmée (Confirmé/Paid) trouvée pour {user_email}. "
            f"Extrait du body : {body_text[:800]}"
        )
