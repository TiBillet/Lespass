"""
Tests E2E : validations du formulaire d'adhésion (page standalone).
/ E2E tests: membership form validations (standalone page).

Conversion de tests/playwright/tests/adhesions/20-membership-validations.spec.ts
Le template cible est reunion/views/membership/form.html (avec data-testid).
"""

import random
import re
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _slugify(value):
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


class TestMembershipValidations:
    """Membership form validation errors / Erreurs de validation du formulaire adhésion."""

    def test_membership_form_validation_errors(self, page, create_product):
        """Vérifie les erreurs de validation : email mismatch, prix libre vide, champs dynamiques.
        / Checks validation errors: email mismatch, empty free price, dynamic fields.
        """
        random_id = _random_id()
        product_name = f"Adhesion Validation {random_id}"
        price_name = "Tarif Libre"
        user_email = f"jturbeaux+adh{random_id}@pm.me"

        boolean_label = "Consent"
        multi_select_label = "Topics"
        boolean_field_name = _slugify(boolean_label)
        multi_select_field_name = _slugify(multi_select_label)

        # --- Étape 1 : Créer le produit adhésion via API ---
        result = create_product(
            name=product_name,
            description="Produit pour validations adhesion.",
            category="Membership",
            offers=[
                {"name": price_name, "price": "10.00", "freePrice": True},
            ],
            form_fields=[
                {"label": boolean_label, "fieldType": "boolean", "required": True, "order": 1},
                {"label": multi_select_label, "fieldType": "multiSelect", "options": ["A", "B"], "required": True, "order": 2},
            ],
        )
        assert result["ok"], f"Création produit échouée: {result}"
        product_uuid = result["uuid"]

        # --- Étape 2 : Naviguer vers la page formulaire d'adhésion ---
        # La page standalone /memberships/<uuid>/ rend form.html avec tous les data-testid.
        page.goto(f"/memberships/{product_uuid}/")
        page.wait_for_load_state("domcontentloaded")

        membership_form = page.locator("#membership-form")
        expect(membership_form).to_be_visible()

        # --- Étape 3 : Vérifier les champs requis ---
        email_input = page.locator("#membership-email")
        confirm_input = page.locator("#confirm-email")
        first_name_input = page.locator('input[name="firstname"]')
        last_name_input = page.locator('input[name="lastname"]')

        expect(email_input).to_have_attribute("required", "")
        expect(confirm_input).to_have_attribute("required", "")
        expect(first_name_input).to_have_attribute("required", "")
        expect(last_name_input).to_have_attribute("required", "")

        acknowledge_input = page.locator("#acknowledge")
        if acknowledge_input.count() > 0 and acknowledge_input.is_visible():
            expect(acknowledge_input).to_have_attribute("required", "")

        # --- Étape 4 : Email mismatch ---
        submit_button = page.locator("#membership-submit")
        boolean_input = page.locator(
            f'[data-testid="membership-form-field-{boolean_field_name}"]'
        ).first
        multi_select_input = page.locator(
            f'[data-testid="membership-form-field-{multi_select_field_name}"]'
        ).first
        custom_amount_input = page.locator('input[name^="custom_amount_"]').first

        first_name_input.fill("Test")
        last_name_input.fill("User")
        if acknowledge_input.count() > 0 and acknowledge_input.is_visible():
            acknowledge_input.check()
        if custom_amount_input.is_visible():
            custom_amount_input.fill("12")
        if boolean_input.is_visible():
            boolean_input.check()
        if multi_select_input.is_visible():
            multi_select_input.check()

        email_input.fill(user_email)
        confirm_input.fill(f"{user_email}.bad")
        submit_button.click()

        # L'email mismatch déclenche setCustomValidity → validity.valid = false
        is_valid = confirm_input.evaluate("(el) => el.validity.valid")
        assert is_valid is False, "Le champ confirm devrait être invalide"

        validation_message = confirm_input.evaluate("(el) => el.validationMessage")
        assert "email" in (validation_message or "").lower() or "Email" in (validation_message or ""), (
            f"Le message de validation devrait contenir 'email', got: {validation_message}"
        )

        # --- Étape 5 : Prix libre vide ---
        confirm_input.fill(user_email)
        # Vider le montant et soumettre
        custom_amount_input.fill("")
        submit_button.click()

        # Le prix libre required est validé par le JS htmx:configRequest
        # Vérifier via la classe is-invalid ajoutée par le JS
        page.wait_for_timeout(300)
        is_invalid = custom_amount_input.evaluate(
            "(el) => el.classList.contains('is-invalid') || !el.validity.valid"
        )
        assert is_invalid, "Le champ montant devrait être invalide quand vide"
        custom_amount_input.fill("12")

        # --- Étape 6 : Champs dynamiques requis ---
        if boolean_input.is_visible():
            boolean_input.uncheck()
        if multi_select_input.is_visible():
            multi_select_input.uncheck()
        submit_button.click()

        # Les erreurs data-bl-error et data-ms-error deviennent visibles
        page.wait_for_timeout(300)
        boolean_error = page.locator("[data-bl-error]").first
        multi_select_error = page.locator("[data-ms-error]").first
        expect(boolean_error).to_be_visible()
        expect(multi_select_error).to_be_visible()
