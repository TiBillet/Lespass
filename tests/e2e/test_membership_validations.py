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


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.e2e, pytest.mark.adhesion]


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _slugify(value):
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


class TestMembershipValidations:
    """Membership form validation errors / Erreurs de validation du formulaire adhésion."""

    def test_membership_form_validation_errors(
        self, page, create_product, login_as, django_shell
    ):
        """Vérifie les erreurs de validation : prix libre vide, champs dynamiques.
        Adhérer exige d'être connecté : l'email est celui du compte, en lecture seule.
        / Checks validation errors: empty free price, dynamic fields.
        Joining requires login: the email is the account's, read-only.
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

        # --- Étape 1 bis : Se connecter. login_as exige un compte existant, activé ---
        # / Step 1 bis: log in. login_as needs an existing, activated account.
        django_shell(
            "from AuthBillet.utils import get_or_create_user\n"
            f"acheteur = get_or_create_user('{user_email}', send_mail=False)\n"
            "acheteur.is_active = True\n"
            "acheteur.save()\n"
        )
        login_as(page, user_email)

        # --- Étape 2 : Naviguer vers la page formulaire d'adhésion ---
        # La page standalone /memberships/<uuid>/ rend form.html avec tous les data-testid.
        page.goto(f"/memberships/{product_uuid}/")
        page.wait_for_load_state("domcontentloaded")

        membership_form = page.locator("#membership-form")
        expect(membership_form).to_be_visible()

        # --- Étape 3 : Vérifier les champs requis ---
        # L'email est celui du compte, en lecture seule.
        # / The email is the account's, read-only.
        email_input = page.locator('[data-testid="membership-email"]')
        expect(email_input).to_have_value(user_email)
        expect(email_input).to_have_attribute("readonly", "")
        first_name_input = page.locator('input[name="firstname"]')
        last_name_input = page.locator('input[name="lastname"]')

        expect(first_name_input).to_have_attribute("required", "")
        expect(last_name_input).to_have_attribute("required", "")

        # La case « acknowledge » n'existe que si le produit a un lien vers des mentions
        # legales : le produit de ce test n'en a pas, elle n'est donc pas concernee.
        # / The acknowledge box only exists with a legal link: not the case here.

        # --- Étape 4 : Remplir le formulaire (sans l'envoyer) ---
        # / Step 4: fill the form (without sending it).
        submit_button = page.locator("#membership-submit")
        boolean_input = page.locator(
            f'[data-testid="membership-form-field-{boolean_field_name}"]'
        ).first
        multi_select_input = page.locator(
            f'[data-testid="membership-form-field-{multi_select_field_name}"]'
        ).first
        custom_amount_input = page.locator('input[name^="custom_amount_"]').first

        # Le produit cree a l'etape 1 porte un prix libre et deux champs obligatoires :
        # ils sont TOUS attendus. / The product has a free price and two required fields.
        first_name_input.fill("Test")
        last_name_input.fill("User")
        expect(custom_amount_input).to_be_visible()
        custom_amount_input.fill("12")
        expect(boolean_input).to_be_visible()
        boolean_input.check()
        expect(multi_select_input).to_be_visible()
        multi_select_input.check()

        # --- Étape 5 : Prix libre vide ---
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
        boolean_input.uncheck()
        multi_select_input.uncheck()
        submit_button.click()

        # Les erreurs data-bl-error et data-ms-error deviennent visibles
        page.wait_for_timeout(300)
        boolean_error = page.locator("[data-bl-error]").first
        multi_select_error = page.locator("[data-ms-error]").first
        expect(boolean_error).to_be_visible()
        expect(multi_select_error).to_be_visible()
