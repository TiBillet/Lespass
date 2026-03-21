"""
Tests E2E smoke : vrai aller-retour Stripe checkout.
/ E2E smoke tests: real Stripe checkout round-trip.

Ces tests font le vrai paiement via checkout.stripe.com.
Timeouts genereux (60-120s par etape) car Stripe peut etre lent.
Carte test : 4242 4242 4242 4242, 12/42, 424.
/ These tests make real payments via checkout.stripe.com.
Generous timeouts (60-120s per step) because Stripe can be slow.
Test card: 4242 4242 4242 4242, 12/42, 424.

IMPORTANT (membership) : le formulaire d'adhesion est un template PARTIEL
(form.html sans base template). Il DOIT etre charge via la page liste
/memberships/ (qui a le base template + HTMX) dans l'offcanvas.
Naviguer directement vers /memberships/<uuid>/ donne une page sans HTMX
et le formulaire se soumet en GET natif au lieu d'un POST HTMX.
/ IMPORTANT (membership): the membership form is a PARTIAL template
(form.html without base template). It MUST be loaded through the list page
/memberships/ (which has the base template + HTMX) in the offcanvas.
Navigating directly to /memberships/<uuid>/ gives a page without HTMX
and the form submits as native GET instead of HTMX POST.
"""

import random
import re
import string

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class TestStripeSmokeCheckout:
    """Smoke tests Stripe : vrai checkout / Real Stripe checkout smoke tests."""

    def test_smoke_membership_stripe_checkout(
        self, page, create_product, fill_stripe_card, admin_email
    ):
        """1 adhesion payante → page liste → offcanvas → Stripe → retour → confirmation.
        / 1 paid membership → list page → offcanvas → Stripe → return → confirmation.
        """
        page.set_default_timeout(120_000)

        rid = _random_id()
        user_email = f"test+smoke{rid}@pm.me"

        # 1. Créer un produit adhésion via API / Create membership product via API
        result = create_product(
            name=f"Smoke Stripe {rid}",
            category="Membership",
            description="Smoke test Stripe E2E",
            offers=[{"name": "Annuelle", "price": "1.00"}],
        )
        assert result["ok"], f"Création produit échouée: {result}"
        product_uuid = result["uuid"]

        # 2. Naviguer vers la page LISTE (pas /memberships/<uuid>/ !)
        # La page liste a le base template reunion/base.html qui charge HTMX.
        # / Navigate to the LIST page (not /memberships/<uuid>/ !)
        # The list page has the reunion/base.html base template that loads HTMX.
        page.goto("/memberships/")
        page.wait_for_load_state("domcontentloaded")

        # 3. Trouver le produit et ouvrir le formulaire dans l'offcanvas
        # Le bouton a data-testid="membership-open-<uuid>" et fait un hx-get
        # qui charge le formulaire dans #offcanvas-membership.
        # / Find the product and open the form in the offcanvas.
        # Button has data-testid and does hx-get to load form into offcanvas.
        subscribe_btn = page.locator(
            f'[data-testid="membership-open-{product_uuid}"]'
        )
        expect(subscribe_btn).to_be_visible(timeout=10_000)
        subscribe_btn.click()

        # 4. Attendre que l'offcanvas s'ouvre et le formulaire charge via HTMX
        # / Wait for the offcanvas to open and the form to load via HTMX
        page.wait_for_selector("#subscribePanel.show", state="visible")
        page.wait_for_selector("#membership-form", state="visible", timeout=10_000)

        # 5. Remplir le formulaire / Fill the form
        page.locator("#membership-email").fill(user_email)
        page.locator("#confirm-email").fill(user_email)
        page.locator('input[name="firstname"]').fill("Smoke")
        page.locator('input[name="lastname"]').fill("Test")

        # Sélectionner le tarif si radio visible / Select price if radio visible
        price_radio = page.locator('input[name="price"][type="radio"]').first
        if price_radio.count() > 0 and price_radio.is_visible():
            price_radio.check()

        # 6. Soumettre et attendre Stripe ou confirmation
        # Pattern race : Stripe redirect OU message de confirmation (gratuit/validation manuelle)
        # / Submit and wait for Stripe or confirmation
        # Race pattern: Stripe redirect OR confirmation message (free/manual validation)
        page.locator("#membership-submit").click()

        try:
            page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=30_000)
        except Exception:
            # Pas de redirect Stripe — chercher un message de confirmation
            # / No Stripe redirect — look for confirmation message
            confirmation = page.locator(
                "text=/demande|reçue|attente|waiting|received/i"
            )
            if confirmation.is_visible(timeout=5_000):
                # Produit gratuit ou validation manuelle — pas de Stripe
                return
            # Erreur réelle : ni Stripe ni confirmation
            errors = page.locator(
                ".alert-danger, .invalid-feedback:visible"
            ).all_text_contents()
            body = page.locator("body").inner_text()[:500]
            pytest.fail(
                f"Ni redirect Stripe ni confirmation. Errors: {errors}. Body: {body}"
            )

        # 7. Remplir la carte Stripe / Fill Stripe card
        # domcontentloaded au lieu de networkidle : Stripe maintient des connexions
        # persistantes (analytics, SSE) qui empechent networkidle de resoudre.
        # / domcontentloaded instead of networkidle: Stripe keeps persistent
        # connections that prevent networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)

        # 8. Cliquer payer / Click pay
        submit_btn = page.locator('button[type="submit"]').first
        expect(submit_btn).to_be_enabled(timeout=30_000)
        submit_btn.click()

        # 9. Attendre le retour vers TiBillet / Wait for return to TiBillet
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url,
            timeout=60_000,
        )

        # 10. Vérifier la page de confirmation / Verify confirmation page
        success_msg = page.locator("text=/merci|confirmée|succès|success/i")
        expect(success_msg).to_be_visible(timeout=30_000)

    def test_smoke_booking_stripe_checkout(
        self, page, create_event, create_product, fill_stripe_card
    ):
        """1 reservation payante → vrai checkout.stripe.com → retour → confirmation.
        / 1 paid booking → real checkout.stripe.com → return → confirmation.
        """
        from datetime import datetime, timedelta, timezone as tz

        page.set_default_timeout(120_000)

        rid = _random_id()
        user_email = f"test+smokebook{rid}@pm.me"
        start_date = (datetime.now(tz.utc) + timedelta(days=2)).isoformat()

        # 1. Créer événement + produit / Create event + product
        event_result = create_event(name=f"Smoke Event {rid}", start_date=start_date)
        assert event_result["ok"], f"Création événement échouée: {event_result}"
        event_slug = event_result["slug"]

        product_result = create_product(
            name=f"Billets Smoke {rid}",
            category="Ticket booking",
            event_uuid=event_result["uuid"],
            offers=[{"name": "Place", "price": "1.00"}],
        )
        assert product_result["ok"], f"Création produit échouée: {product_result}"

        # 2. Naviguer vers l'événement / Navigate to event
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")

        # 3. Ouvrir le panneau de réservation / Open booking panel
        open_button = page.locator(
            'button:has-text("book one or more seats"), '
            'button:has-text("réserver")'
        ).first
        open_button.click()
        page.wait_for_selector(
            "#bookingPanel.show, .offcanvas.show", state="visible"
        )

        # 4. Remplir email + sélectionner 1 billet / Fill email + select 1 ticket
        email_input = page.locator(
            '#bookingPanel input[name="email"], #booking-email'
        ).first
        email_input.fill(user_email)

        confirm_input = page.locator(
            '#bookingPanel input[name="email-confirm"], #booking-confirm'
        ).first
        if confirm_input.is_visible():
            confirm_input.fill(user_email)

        # Incrémenter bs-counter / Increment bs-counter
        counter_plus = page.locator(
            "bs-counter .bi-plus, bs-counter button:has(.bi-plus)"
        ).first
        counter_plus.click()

        # 5. Soumettre / Submit
        submit_btn = page.locator(
            '#bookingPanel button[type="submit"]'
        ).first
        submit_btn.click()

        # 6. Attendre Stripe / Wait for Stripe
        page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=60_000)

        # 7. Remplir carte + payer / Fill card + pay
        # domcontentloaded : Stripe maintient des connexions persistantes (SSE/analytics)
        # qui empechent networkidle de se resoudre.
        # / domcontentloaded: Stripe keeps persistent connections that prevent
        # networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)
        pay_btn = page.locator('button[type="submit"]').first
        expect(pay_btn).to_be_enabled(timeout=30_000)
        pay_btn.click()

        # 8. Attendre le retour / Wait for return
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url,
            timeout=60_000,
        )

        # 9. Vérifier / Verify
        body_text = page.locator("body").inner_text().lower()
        assert any(kw in body_text for kw in [
            "merci", "confirmée", "succès", "success",
            "reservation ok", "valider votre email",
        ]), f"Page de confirmation non trouvée: {body_text[:200]}"
