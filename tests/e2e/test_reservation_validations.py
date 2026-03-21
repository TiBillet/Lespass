"""
Tests E2E : validations du formulaire de réservation.
/ E2E tests: booking form validations.

Conversion de tests/playwright/tests/evenements/18-reservation-validations.spec.ts
"""

import random
import re
import string
from datetime import datetime, timedelta, timezone

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _slugify(value):
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


class TestReservationValidations:
    """Booking form validation errors / Erreurs de validation du formulaire de réservation."""

    def test_booking_form_validation_errors(
        self, page, create_event, create_product, setup_test_data
    ):
        """Vérifie les erreurs : email mismatch, aucun billet, prix libre, champs dynamiques, code promo.
        / Checks errors: email mismatch, no ticket, free price, dynamic fields, promo code.
        """
        random_id = _random_id()
        event_name = f"E2E Reservation Validation {random_id}"
        product_name = f"Billets Validation {random_id}"
        price_name = "Tarif Libre Test"
        promo_code = f"PROMO-{random_id}"
        user_email = f"jturbeaux+resa{random_id}@pm.me"
        start_date = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

        boolean_label = "Consent"
        multi_select_label = "Topics"
        boolean_field_name = _slugify(boolean_label)
        multi_select_field_name = _slugify(multi_select_label)

        # --- Étape 1 : Créer événement + produit ---
        event_result = create_event(
            name=event_name,
            start_date=start_date,
            options_radio=["Option Radio A"],
            options_checkbox=["Option Check A"],
        )
        assert event_result["ok"], f"Création événement échouée: {event_result}"
        event_slug = event_result["slug"]

        product_result = create_product(
            name=product_name,
            description="Produit pour valider les erreurs de formulaire.",
            category="Ticket booking",
            event_uuid=event_result["uuid"],
            offers=[
                {"name": price_name, "price": "5.00", "freePrice": True},
            ],
            form_fields=[
                {"label": boolean_label, "fieldType": "boolean", "required": True, "order": 1},
                {"label": multi_select_label, "fieldType": "multiSelect", "options": ["A", "B"], "required": True, "order": 2},
            ],
        )
        assert product_result["ok"], f"Création produit échouée: {product_result}"

        # --- Étape 2 : Créer un code promo ---
        promo_result = setup_test_data(
            "create_promotional_code",
            product=product_name,
            code_name=promo_code,
            discount_rate="10",
        )
        assert promo_result.get("status") == "success", (
            f"Création code promo échouée: {promo_result}"
        )

        # --- Étape 3 : Ouvrir le formulaire de réservation ---
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")

        open_button = page.locator(
            '[data-testid="booking-open-panel"], '
            'button:has-text("book one or more seats"), '
            'button:has-text("réserver")'
        ).first
        open_button.click()
        page.wait_for_selector(
            "#bookingPanel.show, .offcanvas.show", state="visible"
        )

        booking_form = page.locator(
            '[data-testid="booking-form"], #reservation_form'
        ).first
        expect(booking_form).to_be_visible()

        # --- Étape 4 : Vérifier les champs requis ---
        email_input = page.locator(
            '[data-testid="booking-email"], #booking-email'
        ).first
        confirm_input = page.locator(
            '[data-testid="booking-email-confirm"], #booking-confirm'
        ).first
        expect(email_input).to_have_attribute("required", "")
        expect(confirm_input).to_have_attribute("required", "")

        # --- Étape 5 : Email mismatch ---
        submit_button = page.locator(
            '[data-testid="booking-submit"], #bookingPanel button[type="submit"]'
        ).first
        boolean_input = page.locator(
            f'[data-testid="booking-form-field-{boolean_field_name}"], '
            f'input[name="form__{boolean_field_name}"]'
        ).first
        multi_select_input = page.locator(
            f'[data-testid="booking-form-field-{multi_select_field_name}"], '
            f'input[name="form__{multi_select_field_name}"]'
        ).first
        price_block = page.locator(
            '[data-testid^="booking-price-"], .js-order'
        ).filter(has_text=price_name).first
        option_radio = page.locator('[data-testid^="booking-option-radio-"]').first
        option_checkbox = page.locator('[data-testid^="booking-option-checkbox-"]').first

        email_input.fill(user_email)
        confirm_input.fill(f"{user_email}.bad")

        if boolean_input.is_visible():
            boolean_input.check()

        # Incrémenter le bs-counter à 1 via evaluate / Set bs-counter to 1
        price_block.evaluate(
            """(block) => {
                const counter = block.querySelector('bs-counter');
                if (counter) {
                    counter.value = 1;
                    counter.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }"""
        )

        custom_amount_input = price_block.locator('input[name^="custom_amount_"]').first
        if custom_amount_input.is_visible():
            custom_amount_input.fill("7")
        if option_radio.is_visible():
            option_radio.check()
        if option_checkbox.is_visible():
            option_checkbox.check()
        if multi_select_input.is_visible():
            multi_select_input.check()

        submit_button.click()

        is_valid = confirm_input.evaluate("(el) => el.validity.valid")
        assert is_valid is False, "Le champ confirm devrait être invalide"

        validation_message = confirm_input.evaluate("(el) => el.validationMessage")
        assert "emails" in (validation_message or "").lower(), (
            f"Le message devrait contenir 'emails', got: {validation_message}"
        )

        if boolean_input.is_visible():
            boolean_input.uncheck()

        # --- Étape 6 : Aucun billet sélectionné ---
        # Remettre tous les bs-counter à 0 / Reset all bs-counters to 0
        page.evaluate(
            """() => {
                document.querySelectorAll('bs-counter').forEach((counter) => {
                    counter.value = 0;
                    counter.dispatchEvent(new CustomEvent('bs-counter:update', { bubbles: true }));
                });
            }"""
        )

        confirm_input.fill(user_email)
        if boolean_input.is_visible():
            boolean_input.check()
        if option_radio.is_visible():
            option_radio.check()
        if option_checkbox.is_visible():
            option_checkbox.check()
        if multi_select_input.is_visible():
            multi_select_input.check()

        submit_button.click()

        no_ticket_error = page.locator(
            '[data-testid="booking-no-ticket-error"], #booking-form-error'
        ).first
        expect(no_ticket_error).to_be_visible()

        # --- Étape 7 : Prix libre — vérifier min et required ---
        price_block.evaluate(
            """(block) => {
                const counter = block.querySelector('bs-counter');
                if (counter) {
                    counter.value = 1;
                    counter.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }"""
        )

        expect(custom_amount_input).to_have_attribute("min", "5.00")
        expect(custom_amount_input).to_have_attribute("required", "")
        custom_amount_input.fill("7")

        # --- Étape 8 : Champs dynamiques requis ---
        if boolean_input.is_visible():
            boolean_input.uncheck()
        if multi_select_input.is_visible():
            multi_select_input.uncheck()

        submit_button.click()

        boolean_error = page.locator(
            f'[data-testid="booking-form-error-{boolean_field_name}"], [data-bl-error]'
        ).first
        multi_select_error = page.locator(
            f'[data-testid="booking-form-error-{multi_select_field_name}"], [data-ms-error]'
        ).first
        expect(boolean_error).to_be_visible()
        expect(multi_select_error).to_be_visible()

        # --- Étape 9 : Code promo visible ---
        promo_input = page.locator(
            '[data-testid="booking-promo-code"], #promotional-code'
        ).first
        expect(promo_input).to_be_visible()
