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


# Familles de tests : `make e2e-visible <famille>` (liste : make help, ou pytest.ini).
# / Test families: `make e2e-visible <family>` (list: make help, or pytest.ini).
pytestmark = [pytest.mark.e2e, pytest.mark.billetterie]


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _slugify(value):
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


class TestReservationValidations:
    """Booking form validation errors / Erreurs de validation du formulaire de réservation."""

    def test_booking_form_validation_errors(
        self, page, create_event, create_product, setup_test_data, login_as, django_shell
    ):
        """Vérifie les erreurs : aucun billet, prix libre, champs dynamiques, code promo.
        Réserver exige d'être connecté : l'email est celui du compte, en lecture seule.
        / Checks errors: no ticket, free price, dynamic fields, promo code.
        Booking requires login: the email is the account's, read-only.
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

        # --- Étape 3 : Se connecter, puis ouvrir le formulaire de réservation ---
        # login_as exige un compte existant : on le crée, activé.
        # / login_as needs an existing account: create it, activated.
        django_shell(
            "from AuthBillet.utils import get_or_create_user\n"
            f"acheteur = get_or_create_user('{user_email}', send_mail=False)\n"
            "acheteur.is_active = True\n"
            "acheteur.save()\n"
        )
        login_as(page, user_email)
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

        # --- Étape 4 : L'email est celui du compte, en lecture seule ---
        # / Step 4: the email is the account's, read-only.
        email_input = page.locator('[data-testid="booking-email"]')
        expect(email_input).to_have_value(user_email)
        expect(email_input).to_have_attribute("readonly", "")

        # --- Étape 5 : Remplir le formulaire (sans l'envoyer) ---
        # / Step 5: fill the form (without sending it).
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

        # L'evenement (options radio et case) et le produit (prix libre, deux champs
        # obligatoires) sont crees par ce test : tous leurs champs sont ATTENDUS.
        # / The event and product are created by this test: all their fields are EXPECTED.
        expect(boolean_input).to_be_visible()
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
        expect(custom_amount_input).to_be_visible()
        custom_amount_input.fill("7")
        expect(option_radio).to_be_visible()
        option_radio.check()
        expect(option_checkbox).to_be_visible()
        option_checkbox.check()
        expect(multi_select_input).to_be_visible()
        multi_select_input.check()

        expect(boolean_input).to_be_visible()
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

        expect(boolean_input).to_be_visible()
        boolean_input.check()
        expect(option_radio).to_be_visible()
        option_radio.check()
        expect(option_checkbox).to_be_visible()
        option_checkbox.check()
        expect(multi_select_input).to_be_visible()
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
        expect(boolean_input).to_be_visible()
        boolean_input.uncheck()
        expect(multi_select_input).to_be_visible()
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
