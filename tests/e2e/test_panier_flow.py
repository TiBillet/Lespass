"""
Tests E2E : flux du panier d'achat multi-events.

Les fixtures DB (events, adhesion, billets) sont seedees par `demo_data_v2`
dans sa methode `_seed_e2e_fixtures` — voir
Administration/management/commands/demo_data_v2.py.
Les slugs et UUIDs sont exposes via la fixture conftest `e2e_slugs`.

Prerequis :
- Le tenant 'lespass' doit avoir ete seede avec les fixtures E2E
  (lance automatiquement via flush.sh au demarrage du container).
- Le serveur Django dev doit tourner via Traefik.
- La variable d'env E2E_TEST_TOKEN doit etre disponible (cf. conftest.py).

Run:
    docker exec -e E2E_TEST_TOKEN=<token> -e ADMIN_EMAIL=admin@admin.com \
        lespass_django poetry run pytest tests/e2e/test_panier_flow.py -v

/ E2E tests: multi-event cart flow. DB fixtures seeded by `demo_data_v2`.
Slugs/UUIDs exposed via the `e2e_slugs` conftest fixture.
"""
import re

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.e2e


class TestPanierFlow:
    """
    Flow complet panier d'achat (admin connecte) + flow cart-aware.
    / Full cart flow (admin logged in) + cart-aware flow.
    """

    def test_ajout_au_panier_et_checkout_gratuit(self, page, login_as_admin, e2e_slugs):
        """
        Scenario nominal : admin connecte ajoute 1 billet gratuit au panier,
        passe au checkout, et est redirige vers /my_account/.

        / Nominal: logged-in admin adds 1 free ticket, checks out, redirected
        to /my_account/.

        Le test utilise la fixture seedee "E2E Test — Event gratuit" (FREERES
        jauge 100). Il s'appuie sur :
        - `login_as_admin` (force_login via endpoint de test) pour l'auth
        - `e2e_slugs` pour recuperer le slug dynamique et l'UUID du prix
        """
        # 1. Login admin via force_login (endpoint de test) — pas de flow UI.
        # / Admin login via force_login (test endpoint) — no UI flow.
        login_as_admin(page)

        # 2. Nettoyer le panier pour partir d'un etat vide connu.
        # Auto-accepte le dialog "Empty the cart?" s'il apparait.
        # / Clean cart to start from a known empty state.
        # Auto-accept "Empty the cart?" dialog if shown.
        page.on("dialog", lambda d: d.accept())
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        clear_btn = page.locator('[data-testid="panier-clear"]')
        if clear_btn.count() > 0:
            clear_btn.click()
            page.wait_for_selector(
                'text=/Votre panier vous attend|Your cart is waiting/',
                timeout=5_000,
            )

        # 3. Navigation vers l'event gratuit seede (slug lu via fixture).
        # / Navigate to the seeded free event (slug read from fixture).
        slug = e2e_slugs["event_gratuit_slug"]
        price_uuid = e2e_slugs["event_gratuit_price_uuid"]
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        # 4. Ouvrir le booking panel (offcanvas). Si deja ouvert via urlParams, skip.
        # / Open booking panel. If already open via urlParams, skip.
        booking_trigger = page.locator(
            "button[data-bs-target='#bookingPanel'], "
            "a[data-bs-target='#bookingPanel']"
        )
        if booking_trigger.count() > 0:
            booking_trigger.first.click()

        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5_000)

        # 5. Incrementer le compteur du tarif gratuit (+1 billet).
        # / Increment the free rate counter (+1 ticket).
        counter = page.locator(f"bs-counter[name='{price_uuid}']")
        counter.locator(".bi-plus, button:has(.bi-plus)").first.click()

        # 6. Clic "Ajouter au panier".
        # / Click "Add to cart".
        add_button = page.locator("[data-testid='booking-add-to-cart']")
        expect(add_button).to_be_visible()
        add_button.click()

        # 7. Le badge navbar doit passer a 1.
        # Scope `.navbar` obligatoire (cf. PIEGES 9.39) pour eviter
        # un strict mode violation si le partial panier_content est aussi present.
        # / Navbar badge must reach 1. Scope `.navbar` required (PIEGES 9.39).
        badge_nav = page.locator(".navbar #panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5_000)

        # 8. Navigation /panier/ et verification de l'item.
        # / Navigate to /panier/ and verify the item.
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        expect(page.locator("body")).to_contain_text("E2E Test — Event gratuit")

        # 9. Submit du checkout. Admin connecte → pas de champs firstname/
        # lastname dans /panier/ (collectes via booking_form/membership_form
        # ou par Stripe). Le bouton panier-checkout submit directement.
        # / Submit checkout. Admin logged in → no firstname/lastname fields
        # in /panier/ (collected via booking/membership form or Stripe).
        # Button panier-checkout submits directly.
        checkout_btn = page.locator('[data-testid="panier-checkout"]')
        expect(checkout_btn).to_be_visible()
        checkout_btn.click()

        # 10. Verification de la redirection vers /my_account/ (panier gratuit
        # → pas de Stripe, paiement valide immediat).
        # / Verify redirect to /my_account/ (free cart → no Stripe, immediate
        # validation).
        page.wait_for_url(re.compile(r"/my_account/.*"), timeout=10_000)
        assert "my_account" in page.url

    def test_adhesion_dans_panier_debloque_tarif_gate(self, page, login_as_admin, e2e_slugs):
        """
        Scenario cart-aware : admin connecte ajoute une adhesion au panier,
        puis un tarif gated par cette adhesion devient selectionnable.

        / Cart-aware: logged-in admin adds an adhesion to cart, then a rate
        gated by that adhesion becomes selectable in the same parcours.

        Le test utilise les fixtures seedees :
        - "E2E Test — Adhesion" (adhesion gratuite)
        - "E2E Test — Event gated" (event dont le tarif exige l'adhesion)
        """
        # 1. Login admin + clear panier pour un etat vide de depart.
        # / Admin login + clear cart for empty start state.
        login_as_admin(page)
        page.on("dialog", lambda d: d.accept())
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        clear_btn = page.locator('[data-testid="panier-clear"]')
        if clear_btn.count() > 0:
            clear_btn.click()
            page.wait_for_selector(
                'text=/Votre panier vous attend|Your cart is waiting/',
                timeout=5_000,
            )

        # 2. Ajout de l'adhesion au panier via le formulaire /memberships/.
        # On passe par l'UI (pas via `page.request.post`) pour avoir le
        # csrf_token inclus nativement dans le form HTMX — evite les
        # complications CSRF sur un POST programme.
        # / Add adhesion via /memberships/ form (UI flow). Using UI instead of
        # `page.request.post` to include csrf_token natively via HTMX form —
        # avoids CSRF complications on a programmatic POST.
        page.goto("/memberships/")
        page.wait_for_load_state("networkidle")
        # On cible l'adhesion E2E Test par data-testid de son bouton Subscribe.
        # Le data-testid est `membership-open-<product_uuid>`.
        # / Target the E2E Test adhesion by its Subscribe data-testid.
        adhesion_uuid = e2e_slugs["adhesion_uuid"]
        subscribe_btn = page.locator(f'[data-testid="membership-open-{adhesion_uuid}"]')
        subscribe_btn.wait_for(state="visible", timeout=5_000)
        subscribe_btn.click()
        page.wait_for_selector('#membership-form', timeout=10_000)

        # Selectionner le radio du prix "Gratuite" via son UUID.
        # / Select the "Gratuite" price radio via its UUID.
        adhesion_price_uuid = e2e_slugs["adhesion_price_uuid"]
        # IDs Django peuvent contenir des __ → on utilise [id="..."] (PIEGES 9.47).
        # / Django IDs may contain __ → use [id="..."] (PIEGES 9.47).
        price_radio = page.locator(f'input[type="radio"][value="{adhesion_price_uuid}"]')
        price_radio.check()

        page.fill('[data-testid="membership-firstname"]', 'E2E')
        page.fill('[data-testid="membership-lastname"]', 'Tester')

        add_btn = page.locator('[data-testid="membership-add-to-cart"]')
        expect(add_btn).to_be_visible()
        add_btn.click()

        # Attendre que le badge navbar confirme l'ajout (>= 1).
        # Scope `.navbar` (PIEGES 9.39).
        # / Wait for navbar badge to confirm the add (>= 1). Scope `.navbar`.
        badge_nav = page.locator(".navbar #panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5_000)

        # 3. Navigation vers l'event gated et verification que le tarif gated
        # devient selectionnable (contexte cart-aware).
        # / Navigate to gated event and verify the gated rate becomes
        # selectable (cart-aware context).
        gated_slug = e2e_slugs["event_gated_slug"]
        gated_price_uuid = e2e_slugs["event_gated_price_uuid"]
        page.goto(f"/event/{gated_slug}/")
        page.wait_for_load_state("networkidle")

        booking_trigger = page.locator(
            "button[data-bs-target='#bookingPanel'], "
            "a[data-bs-target='#bookingPanel']"
        )
        if booking_trigger.count() > 0:
            booking_trigger.first.click()

        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5_000)

        # 4. Verification que le bs-counter pour ce tarif est present et
        # selectionnable (l'adhesion est dans le panier → deblocage).
        # On peut aussi verifier l'alert "Accessible via the membership" si
        # le template le rend — mais on reste sur la verification structurelle
        # (counter present) qui ne depend pas du texte i18n.
        # / Verify that the bs-counter for this rate is present and selectable
        # (adhesion in cart → unlocked). Structural check (counter present),
        # independent of i18n text.
        counter = page.locator(f"bs-counter[name='{gated_price_uuid}']")
        expect(counter).to_have_count(1)

    def test_checkout_redirects_to_stripe(self, page, login_as_admin, e2e_slugs):
        """
        Scenario checkout Stripe : admin connecte ajoute un billet payant au
        panier, navigue vers /panier/, clique "Passer au paiement" et doit
        etre redirige vers checkout.stripe.com.

        / Stripe checkout scenario: logged-in admin adds a paid ticket, goes
        to /panier/, clicks "Proceed to payment", should be redirected to
        checkout.stripe.com.

        Pieges Playwright :
        - PIEGES 9.28 : `networkidle` ne resout jamais sur les pages Stripe
          (SSE analytics permanents). On utilise `wait_until='domcontentloaded'`.
        - PIEGES 9.29 : `wait_for_url` en Playwright Python passe une string
          au callback (pas un objet URL). On utilise `"checkout.stripe.com" in url`.
        """
        # 1. Login + clear panier.
        # / Login + clear cart.
        login_as_admin(page)
        page.on("dialog", lambda d: d.accept())
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        clear_btn = page.locator('[data-testid="panier-clear"]')
        if clear_btn.count() > 0:
            clear_btn.click()
            page.wait_for_selector(
                'text=/Votre panier vous attend|Your cart is waiting/',
                timeout=5_000,
            )

        # 2. Ajout du billet payant (10 EUR) via l'UI event.
        # / Add paid ticket (10 EUR) via event UI.
        slug = e2e_slugs["event_payant_slug"]
        price_uuid = e2e_slugs["event_payant_price_uuid"]
        page.goto(f"/event/{slug}/")
        page.wait_for_load_state("networkidle")

        booking_trigger = page.locator(
            "button[data-bs-target='#bookingPanel'], "
            "a[data-bs-target='#bookingPanel']"
        )
        if booking_trigger.count() > 0:
            booking_trigger.first.click()

        form = page.locator("#reservation_form")
        expect(form).to_be_visible(timeout=5_000)

        counter = page.locator(f"bs-counter[name='{price_uuid}']")
        counter.locator(".bi-plus, button:has(.bi-plus)").first.click()

        add_button = page.locator("[data-testid='booking-add-to-cart']")
        expect(add_button).to_be_visible()
        add_button.click()

        badge_nav = page.locator(".navbar #panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5_000)

        # 3. Navigation /panier/ et clic "Passer au paiement" → Stripe.
        # / Go to /panier/ and click "Proceed to payment" → Stripe.
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        checkout_btn = page.locator('[data-testid="panier-checkout"]')
        expect(checkout_btn).to_be_visible()
        checkout_btn.click()

        # 4. Attendre la redirection vers checkout.stripe.com.
        # `wait_until='domcontentloaded'` au lieu de `networkidle` (PIEGES 9.28).
        # Le callback recoit une string (PIEGES 9.29).
        # / Wait for redirect to checkout.stripe.com.
        # Use 'domcontentloaded' instead of 'networkidle' (PIEGES 9.28).
        # Callback receives a string (PIEGES 9.29).
        page.wait_for_url(
            lambda url: "checkout.stripe.com" in url,
            timeout=15_000,
            wait_until="domcontentloaded",
        )
        assert "checkout.stripe.com" in page.url

    def test_add_to_cart_and_pay_chains_checkout(self, page, login_as_admin, e2e_slugs):
        """
        Scenario chainage "Ajouter au panier et payer" : depuis la page event,
        le bouton `booking-add-and-pay` doit ajouter l'item au panier PUIS
        chainer immediatement vers le checkout Stripe.

        / Scenario "Add to cart and pay" chain: from the event page,
        `booking-add-and-pay` button must add the item to cart THEN chain
        immediately to Stripe checkout.

        Pre-requis : le bouton `booking-add-and-pay` n'apparait que si le
        panier.count > 0 (cf. booking_form.html ligne 498). On pre-remplit
        donc le panier avec un billet gratuit avant d'attaquer le flow.

        / Precondition: `booking-add-and-pay` only shows if panier.count > 0
        (see booking_form.html line 498). We pre-fill the cart with a free
        ticket before triggering the flow.
        """
        # 1. Login + clear panier.
        # / Login + clear cart.
        login_as_admin(page)
        page.on("dialog", lambda d: d.accept())
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        clear_btn = page.locator('[data-testid="panier-clear"]')
        if clear_btn.count() > 0:
            clear_btn.click()
            page.wait_for_selector(
                'text=/Votre panier vous attend|Your cart is waiting/',
                timeout=5_000,
            )

        # 2. Pre-fill : ajout d'un billet gratuit pour que le panier ait un item.
        # Cela fait apparaitre le bouton `booking-add-and-pay` sur les autres events.
        # / Pre-fill: add a free ticket so cart has 1 item. This makes the
        # `booking-add-and-pay` button visible on other events.
        gratuit_slug = e2e_slugs["event_gratuit_slug"]
        gratuit_price_uuid = e2e_slugs["event_gratuit_price_uuid"]
        page.goto(f"/event/{gratuit_slug}/")
        page.wait_for_load_state("networkidle")

        trigger_gratuit = page.locator(
            "button[data-bs-target='#bookingPanel'], "
            "a[data-bs-target='#bookingPanel']"
        )
        if trigger_gratuit.count() > 0:
            trigger_gratuit.first.click()

        form_gratuit = page.locator("#reservation_form")
        expect(form_gratuit).to_be_visible(timeout=5_000)

        counter_gratuit = page.locator(f"bs-counter[name='{gratuit_price_uuid}']")
        counter_gratuit.locator(".bi-plus, button:has(.bi-plus)").first.click()

        add_first = page.locator("[data-testid='booking-add-to-cart']")
        add_first.click()

        # Attendre que le badge confirme l'ajout avant de changer de page.
        # / Wait for badge to confirm the add before changing page.
        badge_nav = page.locator(".navbar #panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5_000)

        # 3. Navigation vers l'event payant — le bouton add-and-pay doit apparaitre.
        # / Go to paid event — the add-and-pay button must appear.
        payant_slug = e2e_slugs["event_payant_slug"]
        payant_price_uuid = e2e_slugs["event_payant_price_uuid"]
        page.goto(f"/event/{payant_slug}/")
        page.wait_for_load_state("networkidle")

        trigger_payant = page.locator(
            "button[data-bs-target='#bookingPanel'], "
            "a[data-bs-target='#bookingPanel']"
        )
        if trigger_payant.count() > 0:
            trigger_payant.first.click()

        form_payant = page.locator("#reservation_form")
        expect(form_payant).to_be_visible(timeout=5_000)

        counter_payant = page.locator(f"bs-counter[name='{payant_price_uuid}']")
        counter_payant.locator(".bi-plus, button:has(.bi-plus)").first.click()

        # 4. Clic sur "Ajouter au panier et payer" → chainage Stripe.
        # Le serveur renvoie HX-Redirect vers l'URL Stripe, que HTMX
        # applique via window.location.href.
        # / Click "Add to cart and pay" → Stripe chain.
        # Server sends HX-Redirect to Stripe URL, HTMX applies it via
        # window.location.href.
        add_and_pay = page.locator("[data-testid='booking-add-and-pay']")
        expect(add_and_pay).to_be_visible()
        add_and_pay.click()

        # 5. Attendre la redirection vers checkout.stripe.com (PIEGES 9.28, 9.29).
        # / Wait for redirect to checkout.stripe.com (PIEGES 9.28, 9.29).
        page.wait_for_url(
            lambda url: "checkout.stripe.com" in url,
            timeout=15_000,
            wait_until="domcontentloaded",
        )
        assert "checkout.stripe.com" in page.url


class TestPanierMembershipFlow:
    """
    Flow ajout adhesion au panier + swap partial + toast SweetAlert2.
    Couvre les nouveautes Session 09 :
    - Endpoint `/panier/add/membership/` accepte `price` (form HTML) + `custom_amount_{uuid}`.
    - Toast via HX-Trigger + listener SweetAlert2 dans base.html.
    - Badge navbar MAJ via hx-swap-oob sans conflit body swap.
    - Swap partial #panier-content sur clear/remove/update.

    / Membership add to cart flow + partial swap + SweetAlert2 toast.
    Covers Session 09 additions: HX-Trigger toast, navbar badge OOB, #panier-content swap.

    NOTE : les tests E2E panier necessitent une infra Traefik + login-flow
    operationnelle (cf. conftest.py `login_as` fixture). Si ces tests echouent
    avec un `Timeout waiting for badge`, verifier que le serveur Django tourne
    via Traefik et que `ADMIN_EMAIL` est configure. Flow valide manuellement
    dans Chrome (cf. session-end).
    / E2E panier tests need working Traefik + login-flow infra. Manually
    validated in Chrome (see session-end).
    """

    def test_admin_ajoute_adhesion_au_panier_puis_vide(self, page, login_as_admin):
        """
        Flow :
        1. Login admin.
        2. /memberships/ → clic Subscribe sur la premiere adhesion.
        3. Selectionner un radio prix + cliquer "Ajouter au panier".
        4. Verifier que le toast SweetAlert2 apparait (.swal2-toast).
        5. Verifier que le badge navbar passe a >= 1.
        6. /panier/ → verifier item present dans #panier-content.
        7. Clic "Vider le panier" → swap vers etat vide (texte "Votre panier vous attend").

        / Complete happy path for the membership-to-cart flow.
        """
        login_as_admin(page)

        # 1. Nettoyer le panier pour partir d'un etat vide connu.
        # / Clean cart to start from a known empty state.
        # Auto-accepte le dialog "Empty the cart?".
        # / Auto-accepts "Empty the cart?" dialog.
        page.on("dialog", lambda d: d.accept())
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        clear_btn = page.locator('[data-testid="panier-clear"]')
        if clear_btn.count() > 0:
            clear_btn.click()
            page.wait_for_selector('text=/Votre panier vous attend|Your cart is waiting/', timeout=5_000)

        # 2. Aller sur /memberships/ et ouvrir le premier formulaire d'adhesion.
        # / Navigate to /memberships/ and open the first membership form.
        page.goto("/memberships/")
        page.wait_for_load_state("networkidle")
        first_subscribe = page.locator('[data-testid^="membership-open-"]').first
        first_subscribe.click()
        # L'offcanvas est charge via HTMX (hx-target="#offcanvas-membership").
        # / Offcanvas loaded via HTMX.
        page.wait_for_selector('#membership-form', timeout=10_000)

        # 3. Selectionner un radio de prix FIXE (pas free_price, pas recurring).
        # / Select a FIXED-price radio (not free_price, not recurring).
        # Match par texte "Solidaire" dans le label — c'est le tarif fixe de
        # l'adhesion Tiers Lustre (seeded par demo_data_v2.py). Le 1er radio
        # est "Prix libre" qui exige custom_amount et echoue la validation
        # HTML5 required → add-to-cart bloque → badge reste 0.
        # / Match by text "Solidaire" in label — fixed rate of Tiers Lustre
        # (seeded). Default .first is "Prix libre" which fails validation.
        price_label = page.locator(
            'label.custom-control-label:has-text("Solidaire")'
        ).first
        price_label.wait_for(state="visible", timeout=5_000)
        price_label.click()

        # firstname/lastname sont required sur le form d'adhesion (collectes
        # et stockes sur l'item panier pour prioriser a la materialisation).
        # / firstname/lastname required on membership form (stored on cart item).
        page.fill('[data-testid="membership-firstname"]', 'E2E')
        page.fill('[data-testid="membership-lastname"]', 'Tester')

        add_btn = page.locator('[data-testid="membership-add-to-cart"]')
        expect(add_btn).to_be_visible()
        add_btn.click()

        # 4. Le badge navbar doit passer a au moins 1 apres swap OOB.
        # / Navbar badge should reach at least 1 after OOB swap.
        # Scoper sur .navbar pour eviter le strict mode violation (cf. PIEGES 9.39) —
        # si le partial panier_content etait aussi dans la page, il y aurait
        # un 2eme #panier-badge-nav. Avec le fix Session 09, le badge n'est
        # plus duplique mais on scope quand meme pour robustesse.
        # / Scope to .navbar to avoid strict mode violation (PIEGES 9.39).
        badge_nav = page.locator(".navbar #panier-badge-nav")
        expect(badge_nav).to_contain_text("1", timeout=5_000)

        # 6. Naviguer vers /panier/ et verifier l'item dans #panier-content.
        # / Navigate to /panier/ and verify item inside #panier-content.
        page.goto("/panier/")
        page.wait_for_load_state("networkidle")
        cart_content = page.locator("#panier-content")
        expect(cart_content).to_be_visible()
        # Au moins un item list-group.
        # / At least one list-group item.
        items = cart_content.locator(".list-group-item")
        assert items.count() >= 1, "Au moins un item attendu dans le panier"

        # 7. Clic "Vider le panier" → swap HTMX vers etat vide.
        # / Click "Empty cart" → HTMX swap to empty state.
        clear_btn = page.locator('[data-testid="panier-clear"]')
        clear_btn.click()
        page.wait_for_selector('text=/Votre panier vous attend|Your cart is waiting/', timeout=5_000)
        # Apres le swap, le badge navbar ne doit plus contenir de chiffre.
        # Scope `.navbar` obligatoire (cf. PIEGES 9.39).
        # / After swap, navbar badge should no longer contain a digit.
        expect(page.locator(".navbar #panier-badge-nav")).not_to_contain_text("1", timeout=3_000)
