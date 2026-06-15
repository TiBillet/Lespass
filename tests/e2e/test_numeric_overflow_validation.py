"""
Tests E2E : rejet des montants trop grands sur les champs prix libre.
/ E2E tests: oversized amounts rejected on free price fields.

Conversion de tests/playwright/tests/28-numeric-overflow-validation.spec.ts

Reproduit le bug Sentry #7271957907 : un utilisateur a saisi 145000 comme
montant, provoquant un overflow numerique PostgreSQL
(max_digits=8, scale=2 → maximum 999999.99).

On verifie que :
1. L'input HTML a un attribut max
2. Un montant trop grand est rejete cote client (validation HTML5 ou JS)
3. Memes verifications sur le formulaire de reservation

/ Reproduces Sentry issue #7271957907: a user entered 145000 as custom
amount, causing a PostgreSQL numeric overflow. We check the max attribute,
the client-side rejection, and the same on the booking form.
"""

import datetime
import random
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class TestNumericOverflowValidation:
    """Rejet des montants hors limite / Oversized amounts rejection."""

    def test_membership_rejects_oversized_custom_amount(self, page, create_product):
        """L'adhesion a prix libre rejette un montant trop grand cote client.
        / Free-price membership rejects an oversized amount client-side.
        """
        random_id = _random_id()
        product_name = f"Adhesion Overflow {random_id}"
        user_email = f"jturbeaux+overflow{random_id}@pm.me"

        # --- Etape 1 : Creer un produit adhesion a prix libre via API ---
        # / Step 1: Create a free-price membership product via API
        result = create_product(
            name=product_name,
            description="Produit pour tester l'overflow adhesion.",
            category="Membership",
            offers=[
                {"name": "Tarif Libre Overflow", "price": "10.00", "freePrice": True},
            ],
        )
        assert result["ok"], f"Création produit échouée: {result}"
        product_uuid = result["uuid"]

        # --- Etape 2 : Page standalone du formulaire d'adhesion ---
        # Les validations client (HTML5 + scripts inline) fonctionnent sans
        # HTMX sur cette page partielle — piege 9.8 de tests/PIEGES.md.
        # / Step 2: standalone membership form page. Client-side validations
        # work without HTMX on this partial page — trap 9.8 in tests/PIEGES.md.
        page.goto(f"/memberships/{product_uuid}/")
        page.wait_for_load_state("domcontentloaded")
        expect(page.locator("#membership-form")).to_be_visible()

        custom_amount_input = page.locator('input[name^="custom_amount_"]').first
        expect(custom_amount_input).to_be_visible(timeout=5_000)

        # --- Etape 3 : L'input a un attribut max <= 999999.99 ---
        # / Step 3: input has a max attribute <= 999999.99
        max_value = custom_amount_input.get_attribute("max")
        assert max_value, "L'input prix libre doit avoir un attribut max"
        assert float(max_value) <= 999999.99, f"max trop grand : {max_value}"

        # --- Etape 4 : Montant absurde → rejet client ---
        # / Step 4: absurd amount → client-side rejection
        custom_amount_input.click()
        custom_amount_input.fill("999999999999999")

        page.locator("#membership-email").fill(user_email)
        page.locator("#confirm-email").fill(user_email)
        page.locator('input[name="firstname"]').fill("Overflow")
        page.locator('input[name="lastname"]').fill("Test")

        acknowledge_input = page.locator("#acknowledge")
        if acknowledge_input.count() > 0 and acknowledge_input.is_visible():
            acknowledge_input.check()

        page.locator("#membership-submit").click()

        # La validation HTML (attribut max) ou le JS (classe is-invalid)
        # doit rejeter le montant.
        # / HTML validation (max attribute) or JS (is-invalid class)
        # must reject the amount.
        is_html_valid = custom_amount_input.evaluate("(el) => el.validity.valid")
        has_invalid_class = custom_amount_input.evaluate(
            "(el) => el.classList.contains('is-invalid')"
        )
        assert (not is_html_valid) or has_invalid_class, (
            "Le montant hors limite devrait être rejeté "
            f"(htmlValid={is_html_valid}, isInvalid={has_invalid_class})"
        )

        # Pas de redirection vers Stripe / No Stripe redirect
        assert "stripe.com" not in page.url

        # --- Etape 5 : Un montant valide passe la validation HTML ---
        # / Step 5: a valid amount passes HTML validation
        custom_amount_input.fill("15")
        is_html_valid = custom_amount_input.evaluate("(el) => el.validity.valid")
        assert is_html_valid, "Un montant valide (15) devrait passer la validation"

    def test_booking_rejects_oversized_custom_amount(
        self, page, create_event, create_product
    ):
        """La reservation a prix libre rejette un montant trop grand cote client.
        / Free-price booking rejects an oversized amount client-side.
        """
        random_id = _random_id()
        event_name = f"Event Overflow {random_id}"
        product_name = f"Billet Overflow {random_id}"

        # --- Etape 1 : Creer evenement + billet prix libre via API ---
        # / Step 1: create event + free-price ticket via API
        start_date = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=1)
        ).isoformat()

        event_result = create_event(name=event_name, start_date=start_date)
        assert event_result["ok"], f"Création événement échouée: {event_result}"
        event_slug = event_result["slug"]

        product_result = create_product(
            name=product_name,
            description="Produit pour tester l'overflow réservation.",
            category="Ticket booking",
            event_uuid=event_result["uuid"],
            offers=[
                {"name": "Entrée Libre Overflow", "price": "1.00", "freePrice": True},
            ],
        )
        assert product_result["ok"], f"Création produit échouée: {product_result}"

        # --- Etape 2 : Page evenement, ouvrir le panneau reservation ---
        # / Step 2: event page, open booking panel
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        page.get_by_test_id("booking-open-panel").click()
        page.wait_for_timeout(500)

        # --- Etape 3 : Incrementer la quantite pour afficher le prix libre ---
        # Le bouton "+" est le dernier bouton du web component bs-counter.
        # / Step 3: increment quantity to reveal the free price field.
        # The "+" button is the last button inside the bs-counter component.
        counter = page.locator("bs-counter.js-order-amount").first
        expect(counter).to_be_visible()
        counter.get_by_role("button").last.click()
        page.wait_for_timeout(300)

        custom_amount_input = page.locator(".js-order-custom-price").first
        expect(custom_amount_input).to_be_visible(timeout=5_000)

        # L'input a un attribut max <= 999999.99
        # / Input has a max attribute <= 999999.99
        max_value = custom_amount_input.get_attribute("max")
        assert max_value, "L'input prix libre doit avoir un attribut max"
        assert float(max_value) <= 999999.99, f"max trop grand : {max_value}"

        # --- Etape 4 : Montant absurde → invalide par la validation HTML ---
        # / Step 4: absurd amount → invalidated by HTML validation
        custom_amount_input.click()
        custom_amount_input.fill("9999999999")
        is_html_valid = custom_amount_input.evaluate("(el) => el.validity.valid")
        assert is_html_valid is False, (
            "Le montant hors limite devrait être invalidé par l'attribut max"
        )
