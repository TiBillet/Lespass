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
        # Bouton « Connexion » de la barre utilisateur du skin V2 (data-testid,
        # indépendant de la langue et de la mise en page).
        # / Step 2: open the login panel: V2 user bar button (data-testid,
        # independent of language and layout).
        page.locator('[data-testid="user-bar-connexion"]').click()

        # --- Étape 3 : Remplir un email incorrect / Fill an incorrect email ---
        email_input = page.locator("#loginEmail")
        expect(email_input).to_be_visible()
        email_input.fill("not-an-email")

        # La validité se lit AVANT l'envoi : si l'envoi part, HTMX remplace la page, et
        # un nouveau champ vide (donc invalide) rendrait la lecture vraie par accident.
        # / Validity is read BEFORE submitting: a swapped page would show a new, empty field.
        is_html_valid = email_input.evaluate("(el) => el.validity.valid")

        # --- Étape 4 : Soumettre, en notant tout envoi vers /connexion/ ---
        # Le formulaire part en hx-post vers /connexion/ (commun/formulaires/login.html).
        # / Step 4: submit, recording any request sent to /connexion/.
        envois_vers_la_connexion = []
        page.on(
            "request",
            lambda requete: envois_vers_la_connexion.append(requete.url)
            if "/connexion/" in requete.url else None,
        )
        submit_button = page.locator('#loginForm button[type="submit"]')
        submit_button.click()
        page.wait_for_timeout(500)

        # --- Étape 5 : La validation du navigateur bloque l'envoi ---
        # Deux preuves, toutes deux exigées : le champ est invalide (type=email), ET
        # aucune requête n'est partie vers /connexion/. L'URL, elle, ne prouverait rien :
        # la connexion se fait par un lien envoyé par e-mail, elle ne change jamais.
        # / Step 5: browser validation blocks the submission. Both proofs are required:
        # the field is invalid AND no request reached /connexion/.
        assert is_html_valid is False, (
            "Le champ e-mail accepte « not-an-email » : il a perdu type=email."
        )
        assert envois_vers_la_connexion == [], (
            f"Un e-mail mal formé est parti vers /connexion/ : {envois_vers_la_connexion}"
        )
