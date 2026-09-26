"""
Tests E2E : changement de langue (FR/EN).
/ E2E tests: language (FR/EN) switching.

Conversion de tests/playwright/tests/99-theme_language.spec.ts

Deux vérifications :
1. Le dropdown de la navbar change la langue (attribut lang après reload).
2. La page des préférences (/my_account/profile/) change aussi la langue.

Le thème clair/sombre n'est plus testé : le skin V2 est verrouillé en clair
(pages/templates/pages/V2/shell.html), sans bouton ni interrupteur de thème.
/ Light/dark theme is no longer tested: the V2 skin is locked to light.

État global : la langue vit dans le cookie django_language (vue Django
/i18n/setlang/), limité au contexte navigateur du test (fixture `page` =
nouveau contexte par test) — aucune configuration tenant n'est modifiée.
/ Global state: language lives in the django_language cookie, scoped to the
test's browser context — no tenant config touched, nothing to restore.
"""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestThemeLanguage:
    """Changement de thème et de langue / Theme and language switch."""

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

    def test_sync_language_with_preferences_page(self, page, login_as_admin):
        """La page des préférences (/my_account/profile/) pilote aussi la langue
        (select #languageSelect).
        / Preferences page (/my_account/profile/) also drives the language
        (#languageSelect select).
        """
        # --- Étape 1 : Login admin (cookie de session injecté) ---
        # / Step 1: admin login (session cookie injected)
        login_as_admin(page)

        # --- Étape 2 : Page des préférences du compte ---
        # / Step 2: account preferences page
        page.goto("/my_account/profile/")
        page.wait_for_load_state("networkidle")

        html = page.locator("html")
        lang_select = page.locator("#languageSelect")

        # --- Étape 3 : Changer la langue depuis le select ---
        # Le change déclenche un POST /i18n/setlang/ + reload (même JS que
        # la navbar — language-switcher.mjs).
        # / Step 3: change language from the select. The change event
        # triggers POST /i18n/setlang/ + reload (same JS as navbar).
        current_lang = lang_select.input_value()
        target_lang = "en" if current_lang == "fr" else "fr"
        lang_select.select_option(target_lang)

        # --- Étape 4 : Après reload, l'attribut lang a changé ---
        # / Step 4: after reload, lang attribute changed
        page.wait_for_load_state("networkidle")
        expect(html).to_have_attribute("lang", target_lang)
