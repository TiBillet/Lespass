"""
Tests E2E : popup de participation crowds.
/ E2E tests: crowds participation popup.

Conversion de tests/playwright/tests/crowds/23-crowds-participation.spec.ts
"""

import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestCrowdsParticipation:
    """Crowds participation popup / Popup participation crowds."""

    def test_participation_flow_with_sweetalert(self, page, login_as_admin):
        """Valide le flow pro-bono + covenant + mark completed.
        / Validates pro-bono toggle, covenant requirement, and mark completed flow.
        """
        # --- Étape 1 : Login admin ---
        login_as_admin(page)

        # --- Étape 2 : Naviguer vers la liste crowds ---
        page.goto("/crowd/")
        page.wait_for_load_state("networkidle")

        # --- Étape 3 : Ouvrir le premier détail ---
        details_link = page.locator(
            'a:has-text("Détails"), a:has-text("Details")'
        ).first
        expect(details_link).to_be_visible()
        details_link.click()
        page.wait_for_load_state("networkidle")
        expect(page).to_have_url(re.compile(r"/crowd/"))

        # --- Étape 4 : Ouvrir le popup de participation ---
        participate_button = page.locator(
            'button:has-text("Participer"), button:has-text("Participate")'
        ).first
        expect(participate_button).to_be_visible()
        participate_button.click()

        popup = page.locator(".swal2-popup")
        expect(popup).to_be_visible()

        # --- Étape 5 : Valider les éléments du popup ---
        covenant_link = popup.locator(
            'a[href*="movilab.org"], a:has-text("Règles"), a:has-text("Covenant")'
        )
        expect(covenant_link).to_be_visible()
        expect(covenant_link).to_have_attribute("target", "_blank")

        pro_bono_toggle = popup.locator("#part-pro-bono")
        amount_wrap = popup.locator("#part-amt-wrap")

        expect(pro_bono_toggle).to_be_checked()
        expect(amount_wrap).to_be_hidden()

        # --- Étape 6 : Désactiver pro-bono → montant visible ---
        pro_bono_toggle.click()
        expect(pro_bono_toggle).not_to_be_checked()
        expect(amount_wrap).to_be_visible()

        # --- Étape 7 : Submit sans covenant → message de validation ---
        popup.locator("#part-desc").fill("Test participation E2E")
        popup.locator(".swal2-confirm").click()

        validation_msg = popup.locator(".swal2-validation-message")
        expect(validation_msg).to_be_visible()

        # --- Étape 8 : Accepter covenant, remplir montant, submit ---
        popup.locator("#part-covenant").check()
        popup.locator("#part-amt").fill("10")
        popup.locator(".swal2-confirm").click()

        expect(popup).to_be_hidden()

        # --- Étape 9 : Vérifier la participation dans la liste ---
        participation_list = page.locator("#participations_list")
        expect(participation_list).to_contain_text(
            re.compile(r"Pro-bono|Test participation E2E", re.IGNORECASE)
        )

        # --- Étape 10 : Marquer comme terminé ---
        mark_button = page.locator(
            'button:has-text("Marquer terminé"), button:has-text("Mark completed")'
        ).first
        expect(mark_button).to_be_visible()
        mark_button.click()

        completion_popup = page.locator(".swal2-popup")
        expect(completion_popup).to_be_visible()
        expect(completion_popup.locator("#part-time-unit")).to_be_visible()

        completion_popup.locator("#part-time-value").fill("1")
        completion_popup.locator("#part-time-unit").select_option("days")
        completion_popup.locator(".swal2-confirm").click()

        expect(completion_popup).to_be_hidden()

        # --- Étape 11 : Vérifier la durée ---
        expect(participation_list).to_contain_text(
            re.compile(r"1 j|1 d", re.IGNORECASE)
        )
