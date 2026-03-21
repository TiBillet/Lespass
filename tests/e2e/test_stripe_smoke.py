"""
Tests E2E smoke : vrai aller-retour Stripe checkout.
/ E2E smoke tests: real Stripe checkout round-trip.

Ces tests font le vrai paiement via checkout.stripe.com.
Timeouts genereux (90-120s par etape) car Stripe peut etre lent.
Carte test : 4242 4242 4242 4242, 12/42, 424.
/ These tests make real payments via checkout.stripe.com.
Generous timeouts (90-120s per step) because Stripe can be slow.
Test card: 4242 4242 4242 4242, 12/42, 424.

IMPORTANT : ces tests sont marques xfail(strict=False) car :
- Le formulaire adhesion utilise HTMX (HX-Redirect) — Playwright ne detecte
  pas toujours la navigation declenchee par window.location depuis un XHR.
- La page Stripe maintient des connexions persistantes (analytics, SSE)
  qui empechent networkidle de se resoudre.
Ces tests PASSENT quand les conditions reseau sont bonnes et ne bloquent
pas le build quand Stripe est lent ou que HTMX timing diverge.
/ IMPORTANT: these tests are marked xfail(strict=False) because:
- The membership form uses HTMX (HX-Redirect) — Playwright doesn't always
  detect navigation triggered by window.location from an XHR.
- Stripe's page maintains persistent connections (analytics, SSE)
  preventing networkidle from resolving.
These tests PASS when network conditions are good and don't block
the build when Stripe is slow or HTMX timing diverges.
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

    @pytest.mark.xfail(
        reason="HTMX HX-Redirect : Playwright ne detecte pas toujours la navigation "
               "declenchee par window.location depuis un XHR HTMX.",
        strict=False,
    )
    def test_smoke_membership_stripe_checkout(
        self, page, create_product, fill_stripe_card, admin_email
    ):
        """1 adhesion payante → vrai checkout.stripe.com → retour → confirmation.
        / 1 paid membership → real checkout.stripe.com → return → confirmation.
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

        # 2. Naviguer vers le formulaire / Navigate to form
        page.goto(f"/memberships/{product_uuid}/")
        page.wait_for_load_state("domcontentloaded")

        membership_form = page.locator("#membership-form")
        expect(membership_form).to_be_visible()

        # 3. Remplir le formulaire / Fill the form
        page.locator("#membership-email").fill(user_email)
        page.locator("#confirm-email").fill(user_email)
        page.locator('input[name="firstname"]').fill("Smoke")
        page.locator('input[name="lastname"]').fill("Test")

        # Sélectionner le tarif si radio visible / Select price if radio visible
        price_radio = page.locator('input[name="price"][type="radio"]').first
        if price_radio.count() > 0 and price_radio.is_visible():
            price_radio.check()

        # 4. Soumettre / Submit
        page.locator("#membership-submit").click()

        # 5. Attendre la redirection Stripe / Wait for Stripe redirect
        page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=90_000)

        # 6. Remplir la carte Stripe / Fill Stripe card
        # domcontentloaded au lieu de networkidle : Stripe maintient des connexions
        # persistantes (analytics, SSE) qui empechent networkidle de resoudre.
        # / domcontentloaded instead of networkidle: Stripe keeps persistent
        # connections (analytics, SSE) that prevent networkidle from resolving.
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)

        # 7. Cliquer payer / Click pay
        submit_btn = page.locator('button[type="submit"]').first
        expect(submit_btn).to_be_enabled(timeout=30_000)
        submit_btn.click()

        # 8. Attendre le retour / Wait for return
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url.host,
            timeout=120_000,
        )

        # 9. Vérifier la page de confirmation / Verify confirmation page
        success_msg = page.locator("text=/merci|confirmée|succès|success/i")
        expect(success_msg).to_be_visible(timeout=30_000)

    @pytest.mark.xfail(
        reason="Stripe checkout timing : connexions persistantes Stripe (SSE/analytics) "
               "et bs-counter timing peuvent faire echouer le test.",
        strict=False,
    )
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
        page.wait_for_selector("#bookingPanel.show, .offcanvas.show", state="visible")

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
        counter_plus = page.locator("bs-counter .bi-plus, bs-counter button:has(.bi-plus)").first
        counter_plus.click()

        # 5. Soumettre / Submit
        submit_btn = page.locator(
            '#bookingPanel button[type="submit"]'
        ).first
        submit_btn.click()

        # 6. Attendre Stripe / Wait for Stripe
        page.wait_for_url(re.compile(r"checkout\.stripe\.com"), timeout=90_000)

        # 7. Remplir carte + payer / Fill card + pay
        # domcontentloaded : voir commentaire test_smoke_membership ci-dessus
        page.wait_for_load_state("domcontentloaded")
        fill_stripe_card(page, user_email)
        pay_btn = page.locator('button[type="submit"]').first
        expect(pay_btn).to_be_enabled(timeout=30_000)
        pay_btn.click()

        # 8. Attendre le retour / Wait for return
        page.wait_for_url(
            lambda url: "tibillet.localhost" in url.host,
            timeout=120_000,
        )

        # 9. Vérifier / Verify
        body_text = page.locator("body").inner_text().lower()
        assert any(kw in body_text for kw in [
            "merci", "confirmée", "succès", "success",
            "reservation ok", "valider votre email",
        ]), f"Page de confirmation non trouvée: {body_text[:200]}"
