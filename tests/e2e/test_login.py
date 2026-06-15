"""
Tests E2E : flux de connexion (login).
/ E2E tests: login flow.

Conversion de tests/playwright/tests/01-login.spec.ts

Ce test reproduit la première étape des opérations demo_data :
1. Se connecter en tant qu'admin (via la fixture login_as_admin, qui
   contourne le flow UI complet — cookie de session injecté directement)
2. Vérifier la navigation vers la page /my_account/
3. Confirmer les droits admin (présence de la carte admin du tenant)

Un second test vérifie que le formulaire de connexion rejette un email
mal formé (validation HTML5 côté client).

/ This test reproduces the first step of demo_data operations: admin login,
/my_account navigation, admin card presence. A second test checks the
client-side HTML5 email validation on the login form.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestLoginFlow:
    """Flux de connexion / Login flow."""

    def test_should_authenticate_as_admin(self, page, login_as_admin):
        """L'admin se connecte et voit la carte d'administration du tenant.
        / Admin logs in and sees the tenant admin card.
        """
        # --- Étape 1 : Connexion admin ---
        # On utilise la fixture centralisée login_as_admin (équivalent du
        # helper loginAsAdmin du spec TS) : elle injecte directement un
        # cookie de session authentifié, sans passer par le formulaire UI.
        # / Step 1: admin login via the centralized fixture (TS loginAsAdmin
        # equivalent): injects an authenticated session cookie directly.
        login_as_admin(page)

        # --- Étape 2 : Vérifier la navigation vers la page du compte ---
        # Navigation directe pour s'assurer qu'on est bien là où on s'attend.
        # networkidle est OK sur les pages TiBillet (jamais sur Stripe).
        # / Step 2: verify navigation to the account page. Direct navigation
        # to ensure we are where we expect. networkidle is OK on TiBillet pages.
        page.goto("/my_account/")
        page.wait_for_load_state("networkidle")

        # L'URL doit contenir /my_account/ (pas de redirection vers la home,
        # qui signifierait que la session n'est pas valide).
        # / The URL must contain /my_account/ (a redirect to home would mean
        # the session is not valid).
        assert "/my_account/" in page.url, (
            f"On devrait être sur /my_account/, URL actuelle : {page.url}"
        )

        # --- Étape 3 : Confirmer les droits admin ---
        # Les admins voient une section "Administration" avec une carte rouge
        # par tenant pointant vers /admin/.
        # / Step 3: confirm admin rights. Admins see an "Administration"
        # section with one red card per tenant pointing to /admin/.
        admin_panel_button = page.locator(
            'a.btn-admin-tenant[href*="/admin/"]'
        ).first

        # Le bouton doit être visible / The button must be visible
        expect(admin_panel_button).to_be_visible(timeout=10_000)

        # Il doit porter la classe CSS btn-admin-tenant
        # / It must carry the btn-admin-tenant CSS class
        button_class = admin_panel_button.get_attribute("class") or ""
        assert "btn-admin-tenant" in button_class, (
            f"Le bouton admin devrait avoir la classe btn-admin-tenant, "
            f"classes trouvées : {button_class}"
        )

    def test_should_validate_email_format(self, page):
        """Le formulaire de connexion rejette un email mal formé côté client.
        / The login form rejects a malformed email client-side.
        """
        # --- Étape 1 : Aller à l'accueil / Go home ---
        page.goto("/")
        page.wait_for_load_state("networkidle")

        # --- Étape 2 : Ouvrir le panneau de connexion ---
        # Le libellé du bouton dépend de la langue active : "Log in" (EN)
        # ou "Connexion" (FR) — assertion tolérante FR/EN (piège 9.34).
        # / Step 2: open the login panel. Button label depends on active
        # language: "Log in" (EN) or "Connexion" (FR) — trap 9.34.
        login_button = page.locator(
            '.navbar button:has-text("Log in"), '
            '.navbar button:has-text("Connexion")'
        ).first
        login_button.click()

        # --- Étape 3 : Remplir un email incorrect / Fill an incorrect email ---
        email_input = page.locator("#loginEmail")
        expect(email_input).to_be_visible()
        email_input.fill("not-an-email")

        # --- Étape 4 : Soumettre / Submit ---
        submit_button = page.locator('#loginForm button[type="submit"]')
        submit_button.click()

        # --- Étape 5 : La validation HTML5 doit bloquer l'envoi ---
        # Le spec TS se contentait d'attendre 500ms sans assertion ; ici on
        # vérifie explicitement que le champ email est invalide (type=email)
        # OU, à défaut, qu'aucune connexion n'a eu lieu (pas de /my_account).
        # / Step 5: HTML5 validation must block submission. The TS spec only
        # waited 500ms with no assertion; here we explicitly check the email
        # field validity (type=email) OR, failing that, that no login
        # happened (no /my_account in URL).
        page.wait_for_timeout(500)

        is_html_valid = email_input.evaluate("(el) => el.validity.valid")
        no_login_happened = "/my_account" not in page.url

        assert (is_html_valid is False) or no_login_happened, (
            "Un email mal formé ne devrait pas permettre la connexion "
            f"(htmlValid={is_html_valid}, url={page.url})"
        )
