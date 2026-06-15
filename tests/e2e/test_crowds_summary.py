"""
Tests E2E : toggle du résumé crowds sur la page liste.
/ E2E tests: crowds summary toggle on the list page.

Conversion de tests/playwright/tests/24-crowds-summary.spec.ts
Le template cible est crowds/templates/crowds/partial/summary.html
(tous les data-testid `crowds-summary-*` y sont définis).
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestCrowdsSummaryToggle:
    """Toggle du résumé crowds / Crowds summary toggle."""

    def test_summary_details_expand_and_admin_popups(self, page, login_as_admin):
        """Ouvre la page liste /crowd/, vérifie la barre de résumé, les popups
        admin (allocation + financement global), puis le toggle des détails.
        / Opens /crowd/ list page, checks summary bar, admin popups, then the
        details toggle.
        """
        # --- Étape 1 : Connexion admin ---
        # Le spec TS passait par le flow UI (navbar + formulaire + lien
        # TEST MODE). En Python, la fixture login_as_admin injecte
        # directement le cookie de session (plus rapide, plus fiable).
        # / Step 1: admin login via session cookie injection (fixture),
        # bypassing the UI flow used by the TS spec.
        login_as_admin(page)

        # --- Étape 2 : Aller sur la page liste ---
        # / Step 2: go to the list page
        page.goto("/crowd/")
        page.wait_for_load_state("domcontentloaded")

        # --- Étape 3 : Vérifier les cartes du résumé ---
        # / Step 3: check summary cards
        expect(page.locator('[data-testid="crowds-summary"]')).to_be_visible()

        # La barre de résumé est visible / The summary bar is visible
        summary_bar = page.locator('[data-testid="crowds-summary-bar"]')
        expect(summary_bar).to_be_visible()

        # Toutes les stats sont affichées sur la barre de résumé
        # / All stats are displayed on the summary bar
        expect(
            page.locator('[data-testid="crowds-summary-contributors"]')
        ).to_be_visible()
        expect(page.locator('[data-testid="crowds-summary-time"]')).to_be_visible()
        expect(page.locator('[data-testid="crowds-summary-funding"]')).to_be_visible()

        # La carte "sources" est conditionnelle (selon les données du tenant)
        # / The "sources" card is conditional (depends on tenant data)
        sources_card = page.locator('[data-testid="crowds-summary-sources"]')
        if sources_card.count() > 0:
            expect(sources_card).to_be_visible()

        # Section admin (staff/superuser uniquement) — conditionnelle.
        # / Admin section (staff/superuser only) — conditional.
        admin_section = page.locator('[data-testid="crowds-summary-admin"]')
        if admin_section.count() > 0:
            expect(admin_section).to_be_visible()

            # Bouton d'allocation des fonds → popup SweetAlert2
            # / Funding allocation button → SweetAlert2 popup
            alloc_button = page.locator(
                '[data-testid="crowds-summary-funding-allocate-button"]'
            )
            expect(alloc_button).to_be_visible()
            alloc_button.click()

            popup = page.locator(".swal2-popup")
            expect(popup).to_be_visible()
            expect(popup.locator("#alloc-amount")).to_be_visible()

            # Soit des boutons projet, soit un message "aucun projet".
            # Assertion tolérante FR/EN — piège 9.34 de tests/PIEGES.md.
            # / Either project buttons, or a "no project" message.
            # FR/EN tolerant assertion — trap 9.34 in tests/PIEGES.md.
            project_buttons = popup.locator("button[data-uuid]")
            if project_buttons.count() > 0:
                expect(project_buttons.first).to_be_visible()
            else:
                expect(popup).to_contain_text(
                    re.compile(r"Aucun projet disponible|No project available")
                )

            # Fermer la popup (croix si dispo, sinon touche Échap)
            # / Close the popup (close button if any, else Escape key)
            close_button = popup.locator(".swal2-close")
            if close_button.count() > 0:
                close_button.click()
            else:
                page.keyboard.press("Escape")

        # Bouton de contribution au financement global — conditionnel.
        # / Global funding contribution button — conditional.
        global_funding_button = page.locator(
            '[data-testid="crowds-summary-global-funding-button"]'
        )
        if global_funding_button.count() > 0:
            global_funding_button.click()
            popup = page.locator(".swal2-popup")
            expect(popup).to_be_visible()
            expect(popup.locator("#contrib-name")).to_be_visible()
            expect(popup.locator("#contrib-amt")).to_be_visible()
            # FR : "Annuler" / EN : "Cancel"
            popup.locator(
                'button:has-text("Annuler"), button:has-text("Cancel")'
            ).first.click()

        # --- Étape 4 : Vérifier le bouton toggle ---
        # / Step 4: check toggle button
        toggle = page.locator('[data-testid="crowds-summary-toggle-details"]')
        expect(toggle).to_be_visible()
        # FR : "Voir plus de détail..." ou "Afficher plus de détails..."
        # (la traduction FR du .po diffère du msgid source du template)
        # / EN : "See more details..."
        # / FR translation in .po differs from the template's source msgid.
        expect(toggle).to_have_text(
            re.compile(
                r"Voir plus de détail|Afficher plus de détails|See more details"
            )
        )

        # --- Étape 5 : Ouvrir les détails ---
        # Le collapse Bootstrap ajoute la classe "show" après l'animation —
        # expect() avec regex re-essaie jusqu'au timeout.
        # / Step 5: expand details. Bootstrap collapse adds the "show" class
        # after the animation — expect() with regex auto-retries.
        toggle.click()
        details = page.locator('[data-testid="crowds-summary-details"]')
        expect(details).to_have_class(re.compile(r"show"))
        # FR : "Voir moins" / EN : "View less"
        expect(toggle).to_have_text(re.compile(r"Voir moins|View less"))

        # --- Étape 6 : Vérifier un bloc monnaie (conditionnel) ---
        # / Step 6: check a currency block (conditional)
        currency_cards = details.locator(
            '[data-testid="crowds-summary-currency-card"]'
        )
        if currency_cards.count() > 0:
            expect(currency_cards.first).to_be_visible()

        # --- Étape 7 : Vérifier les actions en cours ---
        # Soit la grille d'actions, soit le message vide (bilingue FR/EN).
        # / Step 7: check actions in progress. Either the actions grid,
        # or the empty message (FR/EN bilingual).
        actions_card = details.locator('[data-testid="crowds-summary-actions-card"]')
        expect(actions_card).to_be_visible()
        actions_grid = details.locator('[data-testid="crowds-summary-actions-grid"]')
        # FR : "Aucune action en cours" / EN : "No action in progress"
        actions_empty = details.locator(
            "text=/Aucune action en cours|No action in progress/"
        )
        if actions_grid.count() > 0:
            expect(actions_grid).to_be_visible()
        else:
            expect(actions_empty).to_be_visible()
