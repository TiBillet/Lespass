"""
Tests E2E : configuration generale dans l'admin (django-unfold).
/ E2E tests: general configuration in the admin (django-unfold).

Conversion de tests/playwright/tests/02-admin-configuration.spec.ts

Reproduit la Section 2 de demo_data_operations.md :
"Configuration générale (pour chaque tenant)".

ATTENTION : ce test MODIFIE la configuration globale du tenant lespass
(nom de l'organisation + description courte). Les valeurs d'origine sont
sauvegardees avant modification et restaurees en fin de test (try/finally),
car la DB de dev est partagee et sans rollback.
/ WARNING: this test MODIFIES the global tenant configuration (organisation
name + short description). Original values are saved before the change and
restored in a try/finally block — shared dev DB, no rollback.
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestAdminConfiguration:
    """Configuration admin / Admin configuration."""

    def test_fill_configuration_fields_and_verify_on_homepage(
        self, page, login_as_admin, django_shell
    ):
        """Remplit la configuration dans l'admin et verifie le nom sur l'accueil.
        / Fills the configuration in the admin and checks the name on the homepage.
        """
        # --- Etape 0 : Sauvegarder la configuration d'origine ---
        # On lit organisation + short_description via le shell Django et on
        # encode en base64 pour transporter les valeurs sans probleme
        # d'echappement (quotes, accents). Le code shell n'utilise QUE des
        # quotes simples : django_shell echappe les doubles quotes (cf.
        # conftest), ce qui casserait la syntaxe Python.
        # / Step 0: save the original configuration. Values are base64-encoded
        # to avoid any quoting issue. Shell code uses single quotes ONLY
        # (django_shell escapes double quotes, breaking Python syntax).
        valeurs_origine_b64 = django_shell(
            "import json, base64\n"
            "from BaseBillet.models import Configuration\n"
            "config = Configuration.get_solo()\n"
            "valeurs = {'organisation': config.organisation, "
            "'short_description': config.short_description}\n"
            "print(base64.b64encode(json.dumps(valeurs).encode()).decode())"
        ).strip()
        assert valeurs_origine_b64, (
            "Impossible de lire la configuration d'origine via django_shell"
        )

        try:
            # --- Etape 1 : Connexion admin ---
            # / Step 1: login as admin
            login_as_admin(page)

            # --- Etape 2 : Naviguer vers le panel admin ---
            # networkidle est OK sur les pages TiBillet (piege 9.28 : interdit
            # uniquement sur Stripe).
            # / Step 2: navigate to the admin panel. networkidle is fine on
            # TiBillet pages (trap 9.28: forbidden on Stripe only).
            page.goto("/admin/")
            page.wait_for_load_state("networkidle")
            assert "/admin/" in page.url, (
                f"On devrait être sur le panel admin, url actuelle : {page.url}"
            )

            # --- Etape 3 : Ouvrir la page Configuration ---
            # Configuration est un singleton (django-solo) : l'admin redirige
            # directement la changelist vers le formulaire de modification.
            # / Step 3: open the Configuration page. Configuration is a
            # singleton (django-solo): the changelist redirects straight to
            # the change form.
            page.goto("/admin/BaseBillet/configuration/")
            page.wait_for_load_state("networkidle")
            assert "configuration" in page.url, (
                f"L'URL devrait contenir 'configuration', url actuelle : {page.url}"
            )

            # --- Etape 4 : Remplir les champs de configuration ---
            # Comme dans le spec TS, on ne remplit que si le champ existe
            # (la config Unfold peut masquer certains champs).
            # / Step 4: fill the configuration fields. Like the TS spec, we
            # only fill when the field exists (Unfold may hide some fields).
            organisation_input = page.locator('input[name="organisation"]')
            if organisation_input.count() > 0:
                organisation_input.fill("Le Tiers-Lustre")

            short_desc_input = page.locator(
                'input[name="short_description"], '
                'textarea[name="short_description"]'
            )
            if short_desc_input.count() > 0:
                short_desc_input.fill(
                    "Instance de démonstration du collectif imaginaire "
                    "« Le Tiers-Lustre »."
                )

            # --- Etape 5 : Enregistrer la configuration ---
            # Selecteur tolerant FR/EN sur le bouton submit (piege 9.34 :
            # le texte depend de la langue active).
            # / Step 5: save the configuration. FR/EN tolerant selector on
            # the submit button (trap 9.34: text depends on active language).
            save_button = page.locator(
                'button[type="submit"]:has-text("Save"), '
                'button[type="submit"]:has-text("Enregistrer"), '
                'input[type="submit"]'
            ).first
            if save_button.count() > 0:
                save_button.click()
                page.wait_for_load_state("networkidle")

            # --- Etape 6 : Verifier sur la page d'accueil ---
            # Le navbar-brand affiche soit le nom de l'organisation (texte),
            # soit un logo (img) quand le texte est vide.
            # / Step 6: verify on the homepage. The navbar-brand shows either
            # the organisation name (text) or a logo (img) when text is empty.
            page.goto("/")
            page.wait_for_load_state("networkidle")

            org_name = page.locator(".navbar-brand").first
            brand_text = org_name.inner_text()
            if len(brand_text.strip()) == 0:
                # Pas de texte : un logo doit etre visible a la place.
                # / No text: a logo must be visible instead.
                expect(org_name.locator("img")).to_be_visible()
            else:
                expect(org_name).to_contain_text(
                    re.compile(r"Le Tiers-Lustre|Tiers-Lustre|Lespass", re.I)
                )

        finally:
            # --- Restauration : remettre la configuration d'origine ---
            # Toujours executee, meme si une assertion echoue plus haut.
            # / Restore: put the original configuration back. Always runs,
            # even when an assertion fails above.
            django_shell(
                "import json, base64\n"
                "from BaseBillet.models import Configuration\n"
                "valeurs = json.loads(base64.b64decode("
                f"'{valeurs_origine_b64}').decode())\n"
                "config = Configuration.get_solo()\n"
                "config.organisation = valeurs['organisation']\n"
                "config.short_description = valeurs['short_description']\n"
                "config.save()\n"
                "print('restored')"
            )
