"""
Tests E2E : changement de thème (clair/sombre) et de langue (FR/EN).
/ E2E tests: theme (light/dark) and language (FR/EN) switching.

Conversion de tests/playwright/tests/99-theme_language.spec.ts

Trois vérifications :
1. Le bouton de la navbar bascule le thème Bootstrap (attribut data-bs-theme).
2. Le dropdown de la navbar change la langue (attribut lang après reload).
3. La page des préférences (/my_account/profile/) synchronise thème et langue.

État global : le thème vit dans le localStorage et la langue dans le cookie
django_language (vue Django /i18n/setlang/). Les deux sont limités au contexte
navigateur du test (fixture `page` = nouveau contexte par test) — aucune
configuration tenant n'est modifiée, donc rien à restaurer.
/ Global state: theme lives in localStorage, language in the django_language
cookie (/i18n/setlang/ Django view). Both are scoped to the test's browser
context (fresh context per test) — no tenant config touched, nothing to restore.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestThemeLanguage:
    """Changement de thème et de langue / Theme and language switch."""

    def test_toggle_theme_from_navbar(self, page):
        """Le bouton #themeToggle de la navbar bascule data-bs-theme puis revient.
        / Navbar #themeToggle button flips data-bs-theme and back.
        """
        # --- Étape 1 : Page d'accueil ---
        # networkidle OK sur les pages TiBillet (jamais sur Stripe — piège 9.28).
        # / Step 1: homepage. networkidle is fine on TiBillet pages.
        page.goto("/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")

        # --- Étape 2 : Le bouton de thème est visible ---
        # / Step 2: theme toggle button is visible
        theme_toggle = page.locator("#themeToggle")
        expect(theme_toggle).to_be_visible()

        # --- Étape 3 : Lire le thème courant (défaut : light) ---
        # Le localStorage du contexte est vierge, mais le thème initial peut
        # dépendre du système — on lit l'attribut plutôt que de supposer.
        # / Step 3: read current theme (default: light). Fresh localStorage,
        # but initial theme may depend on system — read instead of assuming.
        initial_theme = html.get_attribute("data-bs-theme") or "light"
        target_theme = "light" if initial_theme == "dark" else "dark"

        # --- Étape 4 : Basculer vers le thème cible ---
        # / Step 4: switch to target theme
        theme_toggle.click()
        expect(html).to_have_attribute("data-bs-theme", target_theme)

        # --- Étape 5 : Re-cliquer pour revenir au thème initial ---
        # / Step 5: click again to return to initial theme
        theme_toggle.click()
        expect(html).to_have_attribute("data-bs-theme", initial_theme)

    def test_switch_language_from_navbar(self, page):
        """Le dropdown #languageDropdown change la langue : l'attribut lang
        du <html> reflète la nouvelle langue après rechargement de la page.
        / #languageDropdown switches language: <html> lang attribute reflects
        the new language after the page reloads.
        """
        # --- Étape 1 : Page d'accueil ---
        # / Step 1: homepage
        page.goto("/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")

        # --- Étape 2 : Lire la langue courante ---
        # / Step 2: read current language
        initial_lang = html.get_attribute("lang")

        # --- Étape 3 : Ouvrir le dropdown de langue ---
        # / Step 3: open the language dropdown
        language_dropdown = page.locator("#languageDropdown")
        expect(language_dropdown).to_be_visible()
        language_dropdown.click()

        # --- Étape 4 : Choisir l'autre langue (FR ↔ EN) ---
        # Le bouton POSTe sur /i18n/setlang/ puis recharge la page (voir
        # BaseBillet/static/reunion/js/language-switcher.mjs).
        # / Step 4: pick the other language (FR ↔ EN). The button POSTs to
        # /i18n/setlang/ then reloads the page (language-switcher.mjs).
        target_lang = "en" if initial_lang == "fr" else "fr"
        lang_btn = page.locator(
            f'.language-select-btn[data-lang="{target_lang}"]'
        )
        expect(lang_btn).to_be_visible()
        lang_btn.click()

        # --- Étape 5 : Après reload, l'attribut lang a changé ---
        # / Step 5: after reload, lang attribute changed
        page.wait_for_load_state("networkidle")
        expect(html).to_have_attribute("lang", target_lang)

    def test_sync_theme_and_language_with_preferences_page(
        self, page, login_as_admin
    ):
        """La page des préférences (/my_account/profile/) pilote aussi le thème
        (switch #darkThemeCheck) et la langue (select #languageSelect).
        / Preferences page (/my_account/profile/) also drives theme
        (#darkThemeCheck switch) and language (#languageSelect select).
        """
        # --- Étape 1 : Login admin (cookie de session injecté) ---
        # / Step 1: admin login (session cookie injected)
        login_as_admin(page)

        # --- Étape 2 : Page des préférences du compte ---
        # / Step 2: account preferences page
        page.goto("/my_account/profile/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")
        theme_check = page.locator("#darkThemeCheck")
        lang_select = page.locator("#languageSelect")

        # --- Étape 3 : Basculer le thème depuis le switch ---
        # Si le switch était coché (sombre), le clic repasse en clair,
        # et inversement.
        # / Step 3: toggle theme from the switch. If checked (dark),
        # clicking goes back to light, and vice versa.
        expect(theme_check).to_be_visible(timeout=10_000)
        was_checked = theme_check.is_checked()
        theme_check.click()
        expected_theme = "light" if was_checked else "dark"
        expect(html).to_have_attribute("data-bs-theme", expected_theme)

        # --- Étape 4 : Changer la langue depuis le select ---
        # Le change déclenche un POST /i18n/setlang/ + reload (même JS que
        # la navbar — language-switcher.mjs).
        # / Step 4: change language from the select. The change event
        # triggers POST /i18n/setlang/ + reload (same JS as navbar).
        current_lang = lang_select.input_value()
        target_lang = "en" if current_lang == "fr" else "fr"
        lang_select.select_option(target_lang)

        # --- Étape 5 : Après reload, l'attribut lang a changé ---
        # / Step 5: after reload, lang attribute changed
        page.wait_for_load_state("networkidle")
        expect(html).to_have_attribute("lang", target_lang)
