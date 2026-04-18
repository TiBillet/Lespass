"""
Tests E2E : flux du panier d'achat multi-events.
Session 06 — Taches 6.1, 6.2.

Prerequis :
- Le tenant 'lespass' doit avoir au moins un event FREERES publie avec un slug
- Prerequis Django dev server actif

Run:
    poetry run pytest -q tests/e2e/test_panier_flow.py

/ E2E tests: cart flow multi-events. Prereq: lespass tenant with FREERES event.
"""
import re
import uuid
from datetime import timedelta

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


@pytest.fixture
def event_gratuit_publie():
    """Cree (ou recupere) un event FREERES publie dans le tenant lespass.
    Le tenant doit etre active via un context ailleurs.
    / Create (or get) a published FREERES event in the lespass tenant.
    Tenant must be activated elsewhere.
    """
    from django.utils import timezone
    from django_tenants.utils import tenant_context
    from Customers.models import Client as TenantClient
    from BaseBillet.models import Event, Product

    tenant = TenantClient.objects.get(schema_name="lespass")
    with tenant_context(tenant):
        # Produit FREERES (price 0 auto-cree)
        # / FREERES product (price 0 auto-created)
        prod_key = f"e2e-free-{uuid.uuid4().hex[:8]}"
        product = Product.objects.create(
            name=prod_key,
            categorie_article=Product.FREERES,
        )
        event = Event.objects.create(
            name=f"E2E Free {uuid.uuid4().hex[:8]}",
            slug=f"e2e-free-{uuid.uuid4().hex[:8]}",
            datetime=timezone.now() + timedelta(days=7),
            jauge_max=50,
            published=True,
        )
        event.products.add(product)
        price = product.prices.filter(prix=0).first()
        assert price is not None

        yield {
            "event": event,
            "product": product,
            "price": price,
            "slug": event.slug,
        }


class TestPanierFlow:
    """Flow complet panier d'achat anonyme + flow cart-aware."""

    def test_ajout_au_panier_et_checkout_gratuit(self, page, event_gratuit_publie):
        """
        Scenario nominal : anonyme ajoute 1 billet gratuit au panier,
        passe au checkout, redirige vers my_account.
        / Nominal: anonymous adds 1 free ticket, checks out, redirected to my_account.
        """
        data = event_gratuit_publie
        slug = data["slug"]

        # 1. Aller sur la page event
        # / Go to event page
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        # 2. Ouvrir le booking panel (offcanvas) — le booking_form est dedans
        # / Open booking panel (offcanvas) — booking_form is inside
        # La page event a un bouton qui ouvre le bookingPanel
        # / Event page has a button that opens bookingPanel
        booking_trigger = page.locator("button[data-bs-target='#bookingPanel'], a[data-bs-target='#bookingPanel']")
        if booking_trigger.count() > 0:
            booking_trigger.first.click()
        # Si le panel est deja ouvert via urlParams, skip
        # / If panel already opened via urlParams, skip

        # 3. Attendre que le form booking soit visible
        # / Wait for booking form visible
        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5000)

        # 4. Remplir email (anonyme)
        # / Fill email (anonymous)
        email = f"e2e-{uuid.uuid4().hex[:8]}@example.org"
        page.fill("input[name='email']", email)
        page.fill("input[name='email-confirm']", email)

        # 5. Selectionner 1 billet via le bs-counter
        # / Select 1 ticket via bs-counter
        # bs-counter utilise un + btn / - btn avec name du price
        # / bs-counter uses + btn / - btn with price name
        counter = page.locator(f"bs-counter[name='{data['price'].uuid}']")
        # Increment d'un clic sur le + (icone Bootstrap Icons .bi-plus)
        # / Increment with a click on + (Bootstrap Icons .bi-plus)
        counter.locator(".bi-plus, button:has(.bi-plus)").first.click()

        # 6. Cliquer "Add to cart"
        # / Click "Add to cart"
        add_button = page.locator("[data-testid='booking-add-to-cart']")
        expect(add_button).to_be_visible()
        add_button.click()

        # 7. Verifier le badge panier passe a 1
        # / Verify cart badge shows 1
        page.wait_for_timeout(1000)  # HTMX response
        badge_nav = page.locator("#panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5000)

        # 8. Aller sur /panier/
        # / Go to /panier/
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")

        # 9. Verifier le nom de l'event est dans la liste
        # / Verify event name in list
        expect(page.locator("body")).to_contain_text(data["event"].name)

        # 10. Soumettre le form checkout
        # / Submit checkout form
        page.fill("input[name='first_name']", "E2E")
        page.fill("input[name='last_name']", "Tester")
        page.fill("input[name='email']", email)

        page.click("button:has-text('Proceed to payment'), button:has-text('Payer')")

        # 11. Verifier redirection vers my_account/my_reservations
        # / Verify redirect to my_account/my_reservations
        page.wait_for_url(re.compile(r"/my_account/.*"), timeout=10000)
        assert "my_account" in page.url

    def test_adhesion_dans_panier_debloque_tarif_gate(self, page):
        """
        Scenario cart-aware : utilisateur ajoute adhesion gratuite au panier,
        puis un tarif gate par cette adhesion devient selectionnable.
        / Cart-aware: user adds free membership to cart, then a gated rate
        becomes selectable in the same parcours.
        """
        from datetime import timedelta
        from decimal import Decimal
        from django.utils import timezone
        from django_tenants.utils import tenant_context
        from Customers.models import Client as TenantClient
        from BaseBillet.models import Event, Price, Product

        tenant = TenantClient.objects.get(schema_name="lespass")
        with tenant_context(tenant):
            # Product adhesion gratuite
            # / Free membership product
            prod_adh = Product.objects.create(
                name=f"E2E Adh {uuid.uuid4().hex[:8]}",
                categorie_article=Product.ADHESION,
            )
            price_adh = Price.objects.create(
                product=prod_adh, name="Std",
                prix=Decimal("0.00"), publish=True,
            )
            # Event avec tarif gate
            # / Event with gated rate
            event = Event.objects.create(
                name=f"E2E Gate {uuid.uuid4().hex[:8]}",
                slug=f"e2e-gate-{uuid.uuid4().hex[:8]}",
                datetime=timezone.now() + timedelta(days=5),
                jauge_max=50,
                published=True,
            )
            prod_billet = Product.objects.create(
                name=f"E2E B {uuid.uuid4().hex[:8]}",
                categorie_article=Product.BILLET,
            )
            event.products.add(prod_billet)
            price_gated = Price.objects.create(
                product=prod_billet, name="Adherent",
                prix=Decimal("0.00"), publish=True,
            )
            price_gated.adhesions_obligatoires.add(prod_adh)

            slug = event.slug
            price_adh_uuid = str(price_adh.uuid)
            price_gated_uuid = str(price_gated.uuid)

        # 1. Ajouter l'adhesion au panier via API (shortcut — pas besoin de traverser la page adhesion)
        # / Add membership to cart via API (shortcut — skip membership page traversal)
        response = page.request.post("/panier/add/membership/", data={
            "price_uuid": price_adh_uuid,
        })
        assert response.status == 200

        # 2. Aller sur l'event et verifier que le tarif gate affiche "Accessible via the membership"
        # / Go to event, verify gated rate shows "Accessible via the membership"
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        # Ouvrir le booking panel si besoin
        # / Open booking panel if needed
        booking_trigger = page.locator("button[data-bs-target='#bookingPanel'], a[data-bs-target='#bookingPanel']")
        if booking_trigger.count() > 0:
            booking_trigger.first.click()

        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5000)

        # 3. Verifier que l'alert "Accessible via the membership" est presente
        # / Verify "Accessible via the membership" alert present
        alert = page.locator("text=Accessible via the membership")
        expect(alert).to_be_visible(timeout=3000)

        # 4. Verifier que le bs-counter pour ce tarif est present (donc selectionnable)
        # / Verify bs-counter for this rate is present (thus selectable)
        counter = page.locator(f"bs-counter[name='{price_gated_uuid}']")
        expect(counter).to_have_count(1)
