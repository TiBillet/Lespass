"""
Tests E2E : changement de theme et langue.
/ E2E tests: theme and language switching.

Conversion de tests/playwright/tests/admin/99-theme_language.spec.ts
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestThemeLanguage:
    """Theme and language switching / Changement de theme et langue."""

    def test_toggle_theme(self, page):
        """Toggle dark/light theme via le bouton #themeToggle.
        / Toggle dark/light theme via #themeToggle button.
        """
        page.goto("/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")
        theme_toggle = page.locator("#themeToggle")
        expect(theme_toggle).to_be_visible()

        # Theme initial / Initial theme
        initial_theme = html.get_attribute("data-bs-theme") or "light"
        target_theme = "light" if initial_theme == "dark" else "dark"

        # Switch vers le theme cible / Switch to target theme
        theme_toggle.click()
        expect(html).to_have_attribute("data-bs-theme", target_theme)

        # Switch retour / Switch back
        theme_toggle.click()
        expect(html).to_have_attribute("data-bs-theme", initial_theme)

    def test_switch_language(self, page):
        """Changer la langue via le dropdown #languageDropdown.
        / Switch language via #languageDropdown.
        """
        page.goto("/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")
        initial_lang = html.get_attribute("lang")

        language_dropdown = page.locator("#languageDropdown")
        expect(language_dropdown).to_be_visible()
        language_dropdown.click()

        # Choisir l'autre langue / Choose the other language
        target_lang = "en" if initial_lang == "fr" else "fr"
        lang_btn = page.locator(f'.language-select-btn[data-lang="{target_lang}"]')
        expect(lang_btn).to_be_visible()
        lang_btn.click()

        page.wait_for_load_state("networkidle")
        expect(html).to_have_attribute("lang", target_lang)

    def test_sync_theme_language_preferences(self, page, login_as_admin):
        """Toggle theme et langue depuis la page profil (admin connecte).
        / Toggle theme and language from profile page (logged in admin).
        """
        login_as_admin(page)

        page.goto("/my_account/profile/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")

        # --- Toggle theme depuis les preferences ---
        theme_check = page.locator("#darkThemeCheck")
        if theme_check.is_visible(timeout=5_000):
            is_checked = theme_check.is_checked()
            theme_check.click()
            expected_theme = "light" if is_checked else "dark"
            expect(html).to_have_attribute("data-bs-theme", expected_theme)
        else:
            pytest.skip("#darkThemeCheck non visible sur /my_account/profile/")

        # --- Changer langue depuis les preferences ---
        lang_select = page.locator("#languageSelect")
        if lang_select.is_visible(timeout=5_000):
            current_lang = lang_select.input_value()
            target_lang = "en" if current_lang == "fr" else "fr"
            lang_select.select_option(target_lang)
            page.wait_for_load_state("networkidle")
            expect(html).to_have_attribute("lang", target_lang)
        else:
            pytest.skip("#languageSelect non visible sur /my_account/profile/")
