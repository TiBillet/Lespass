"""
Tests E2E admin tireuses (controlvanne) — Playwright.
/ E2E tests for tap admin (controlvanne) — Playwright.

LOCALISATION : tests/e2e/test_controlvanne_admin.py

Prérequis :
- Serveur Django actif via Traefik
- module_tireuse activé sur le tenant lespass
- Playwright installé (poetry run playwright install chromium)
"""

import pytest


@pytest.mark.usefixtures("page")
class TestControvanneAdmin:
    """Tests admin Unfold pour les tireuses."""

    def test_01_sidebar_tireuses_visible(self, page, login_as_admin):
        """La sidebar contient le lien Taps quand module_tireuse est activé."""
        login_as_admin(page)
        page.goto("/admin/")
        page.wait_for_load_state("networkidle")

        # Chercher le lien Taps dans la sidebar
        taps_link = page.locator("a:has-text('Taps'), a:has-text('Tireuse')")
        assert taps_link.count() > 0, "Le lien Taps/Tireuse n'est pas visible dans la sidebar"

    def test_02_liste_tireuses(self, page, login_as_admin):
        """La page liste des tireuses se charge sans erreur."""
        login_as_admin(page)
        page.goto("/admin/controlvanne/tireusebec/")
        page.wait_for_load_state("networkidle")
        assert page.title()
        content = page.content()
        assert "tireusebec" in page.url.lower() or "Tap" in content

    def test_03_historique_tireuse(self, page, login_as_admin):
        """La page historique des tireuses se charge."""
        login_as_admin(page)
        page.goto("/admin/controlvanne/historiquetireuse/")
        page.wait_for_load_state("networkidle")
        assert page.title()
