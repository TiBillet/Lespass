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

import uuid

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
        # d'echappement (quotes, accents).
        # / Step 0: save the original configuration. Values are base64-encoded
        # to avoid any quoting issue.
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
            # Configuration est un singleton (django-solo) : son formulaire de
            # modification est servi directement a l'URL de liste.
            # / Step 3: open the Configuration page. Configuration is a
            # singleton (django-solo): its change form is served at the list URL.
            page.goto("/admin/BaseBillet/configuration/")
            page.wait_for_load_state("networkidle")

            # --- Etape 4 : Remplir les champs, OBLIGATOIRES ---
            # Un nom unique par run : si l'enregistrement echoue, l'accueil ne
            # peut pas afficher par hasard une valeur laissee par un run precedent.
            # / Step 4: fill the fields, MANDATORY. A unique name per run, so the
            # homepage cannot show a value left over by an earlier run.
            nom_attendu = f"Le Tiers-Lustre {uuid.uuid4().hex[:6]}"
            description_attendue = (
                "Instance de démonstration du collectif imaginaire « Le Tiers-Lustre »."
            )
            organisation_input = page.locator('input[name="organisation"]')
            expect(organisation_input).to_be_visible()
            organisation_input.fill(nom_attendu)

            short_desc_input = page.locator(
                'input[name="short_description"], textarea[name="short_description"]'
            )
            expect(short_desc_input).to_be_visible()
            short_desc_input.fill(description_attendue)

            # --- Etape 5 : Enregistrer, OBLIGATOIRE ---
            # Le bouton « Enregistrer » d'Unfold porte name="_save" (submit_line.html).
            # / Step 5: save, MANDATORY. Unfold's save button has name="_save".
            page.locator('button[name="_save"]').click()
            page.wait_for_load_state("networkidle")

            # --- Etape 6 : La base a bien enregistre les deux valeurs ---
            # / Step 6: the database really stored both values.
            valeurs_en_base = django_shell(
                "from BaseBillet.models import Configuration\n"
                "config = Configuration.get_solo()\n"
                "print('ORGANISATION=' + str(config.organisation))\n"
                "print('DESCRIPTION=' + str(config.short_description))"
            )
            assert f"ORGANISATION={nom_attendu}" in valeurs_en_base, (
                f"Le nom saisi n'a pas ete enregistre : {valeurs_en_base[-300:]}"
            )
            assert f"DESCRIPTION={description_attendue}" in valeurs_en_base, (
                f"La description saisie n'a pas ete enregistree : {valeurs_en_base[-300:]}"
            )

            # --- Etape 7 : Le site public affiche le NOUVEAU nom ---
            # / Step 7: the public site shows the NEW name.
            page.goto("/")
            page.wait_for_load_state("networkidle")
            expect(page.locator('[data-testid="tenant-header-nom"]')).to_have_text(nom_attendu)

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
