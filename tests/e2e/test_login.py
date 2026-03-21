"""
Tests E2E : flux de connexion.
/ E2E tests: login flow.

Conversion de tests/playwright/tests/admin/01-login.spec.ts
/ Converted from tests/playwright/tests/admin/01-login.spec.ts
"""

import re

import pytest


pytestmark = pytest.mark.e2e


class TestLoginFlow:
    """Login Flow / Flux de connexion."""

    def test_authenticate_as_admin(self, page, login_as_admin):
        """Connexion standard avec droits admin.
        / Standard login with admin rights.
        """
        # 1. Login complet via le helper / Full login via helper
        login_as_admin(page)

        # 2. Naviguer vers /my_account/ / Navigate to /my_account/
        page.goto("/my_account/")
        page.wait_for_load_state("networkidle")

        # L'URL doit contenir /my_account/ / URL must contain /my_account/
        assert re.search(r"/my_account/", page.url), (
            f"Expected /my_account/ in URL, got {page.url}"
        )

        # 3. Le bouton Admin panel doit être visible avec la classe btn-outline-danger
        # / Admin panel button must be visible with btn-outline-danger class
        admin_panel_button = page.locator('a[href*="/admin/"]').filter(
            has_text=re.compile(r"Admin panel|Panneau d'administration", re.IGNORECASE)
        )
        admin_panel_button.wait_for(state="visible", timeout=10_000)

        # Vérifier la classe CSS / Check the CSS class
        css_classes = admin_panel_button.get_attribute("class") or ""
        assert "btn-outline-danger" in css_classes, (
            f"Expected btn-outline-danger in classes, got: {css_classes}"
        )

    def test_validate_email_format(self, page):
        """Vérifier la validation du format email dans le formulaire.
        / Check email format validation in the form.
        """
        # 1. Aller à l'accueil / Go home
        page.goto("/")
        page.wait_for_load_state("networkidle")
        url_before = page.url

        # 2. Ouvrir le panneau de connexion / Open login panel
        login_button = page.locator(
            '.navbar button:has-text("Log in"), '
            '.navbar button:has-text("Connexion")'
        ).first
        login_button.click()

        # 3. Remplir un email invalide / Fill an invalid email
        email_input = page.locator("#loginEmail")
        email_input.fill("not-an-email")

        # 4. Soumettre / Submit
        submit_button = page.locator('#loginForm button[type="submit"]')
        submit_button.click()

        # 5. La validation HTML5 bloque l'envoi — l'URL ne change pas
        # / HTML5 validation blocks submission — URL stays the same
        page.wait_for_timeout(500)
        assert page.url == url_before, (
            f"URL changed after invalid email: {page.url}"
        )
