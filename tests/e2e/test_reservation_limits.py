"""
Tests E2E : limites de réservation (stock, max par utilisateur, adhésion requise).
/ E2E tests: reservation limits (stock, max per user, membership required).

Conversion de tests/playwright/tests/19-reservation-limits.spec.ts

Scénario couvert / Covered scenario:
1. Stock épuisé → message "n'est plus disponible" pour un anonyme
2. Max par tarif atteint → message "nombre maximum de réservations" pour le user
3. Max par événement atteint → message sur la page event
4. Tarif réservé aux adhérents → messages anonyme ("Connectez-vous") et
   connecté non-membre ("pour réserver à ce tarif")
5. Après adhésion → le compteur bs-counter redevient visible

NOTE : les fixtures conftest ne couvrent pas la création de réservations,
d'adhésions, ni l'option membershipRequiredProduct sur une offre. On appelle
donc l'API v2 directement depuis ce fichier (mêmes payloads que
tests/playwright/tests/utils/api.ts), sans toucher au conftest.
/ NOTE: conftest fixtures don't cover reservation/membership creation nor the
membershipRequiredProduct offer option. We call the API v2 directly from this
file (same payloads as utils/api.ts), without touching conftest.
"""

import random
import string
from datetime import datetime, timedelta, timezone

import pytest
import requests as http_requests
from playwright.sync_api import expect

# Constantes d'environnement partagées (dual-mode container/hôte — piège 9.7).
# / Shared environment constants (container/host dual-mode — trap 9.7).
from tests.e2e.conftest import API_BASE_URL, API_HOST_HEADER, BASE_URL


pytestmark = pytest.mark.e2e


def _random_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _api_headers(api_key):
    """Construit les headers API v2 (Api-Key + Host si dans le container).
    / Builds API v2 headers (Api-Key + Host header when inside container).
    """
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "Content-Type": "application/json",
    }
    if API_HOST_HEADER:
        headers["Host"] = API_HOST_HEADER
    return headers


def _api_post(api_key, path, payload):
    """POST JSON vers l'API v2, retourne {ok, status, data}.
    / POST JSON to API v2, returns {ok, status, data}.
    """
    resp = http_requests.post(
        f"{API_BASE_URL}{path}",
        headers=_api_headers(api_key),
        json=payload,
        verify=False,
    )
    data = None
    try:
        data = resp.json()
    except ValueError:
        pass
    return {"ok": resp.ok, "status": resp.status_code, "data": data}


def _create_restricted_product(api_key, name, description, event_uuid,
                               offer_name, membership_product_uuid):
    """Crée un produit billet dont le tarif exige une adhésion.

    Le fixture conftest `create_product` ne transmet pas
    `membershipRequiredProduct` : on poste le payload schema.org complet
    nous-mêmes (cf. utils/api.ts et api_v2/serializers.py qui lit cette clé
    directement sur l'offre).
    / Creates a ticket product whose price requires a membership. The conftest
    `create_product` fixture doesn't forward `membershipRequiredProduct`, so we
    post the full schema.org payload ourselves.
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": name,
        "description": description,
        "category": "Free booking",
        "isRelatedTo": {"@type": "Event", "identifier": event_uuid},
        "offers": [
            {
                "@type": "Offer",
                "name": offer_name,
                "price": "0.00",
                "priceCurrency": "EUR",
                "membershipRequiredProduct": membership_product_uuid,
            },
        ],
    }
    return _api_post(api_key, "/api/v2/products/", payload)


def _create_reservation(api_key, event_uuid, email, price_uuid, qty=1,
                        confirmed=True):
    """Crée une réservation confirmée via l'API v2 (équivalent
    createReservationApi de utils/api.ts).
    / Creates a confirmed reservation via API v2 (mirrors createReservationApi).
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "Reservation",
        "reservationFor": {"@type": "Event", "identifier": event_uuid},
        "underName": {"@type": "Person", "email": email},
        "reservedTicket": [
            {
                "@type": "Ticket",
                "identifier": price_uuid,
                "ticketQuantity": qty,
            },
        ],
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "confirmed", "value": confirmed},
        ],
    }
    return _api_post(api_key, "/api/v2/reservations/", payload)


def _create_membership(api_key, price_uuid, email, valid_until):
    """Crée une adhésion gratuite valide via l'API v2 (équivalent
    createMembershipApi de utils/api.ts, paymentMode=FREE).
    / Creates a valid free membership via API v2 (mirrors createMembershipApi).
    """
    payload = {
        "@context": "https://schema.org",
        "@type": "ProgramMembership",
        "member": {
            "@type": "Person",
            "email": email,
            "givenName": "API",
            "familyName": "Member",
        },
        "membershipPlan": {"@type": "Offer", "identifier": price_uuid},
        "validUntil": valid_until,
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "paymentMode", "value": "FREE"},
        ],
    }
    return _api_post(api_key, "/api/v2/memberships/", payload)


def _find_offer_uuid(product_result, offer_name):
    """Retrouve l'identifier (UUID du Price) d'une offre par son nom dans la
    réponse API. / Finds the offer identifier (Price UUID) by name in the API
    response.
    """
    for offer in (product_result.get("offers") or []):
        if offer.get("name") == offer_name:
            return offer.get("identifier")
    return None


def _open_booking_panel(page):
    """Ouvre le panneau de réservation sur la page event courante.
    Sélecteurs tolérants FR/EN comme dans le spec TS d'origine.
    / Opens the booking panel on the current event page. FR/EN tolerant
    selectors, same as the original TS spec.
    """
    open_button = page.locator(
        '[data-testid="booking-open-panel"], '
        'button:has-text("book one or more seats"), '
        'button:has-text("réserver")'
    ).first
    open_button.click()
    page.wait_for_selector("#bookingPanel.show, .offcanvas.show", state="visible")


def _price_block(page, price_name):
    """Localise le bloc tarif (par data-testid ou .js-order) filtré par nom.
    / Locates the price block (data-testid or .js-order) filtered by name.
    """
    return page.locator(
        '[data-testid^="booking-price-"], .js-order'
    ).filter(has_text=price_name).first


def _expect_price_block_text(price_block, fragment_en, fragment_fr):
    """Assertion tolérante FR/EN sur le texte du bloc tarif — piège 9.34.
    / FR/EN tolerant assertion on the price block text — trap 9.34.
    """
    expect(price_block).to_be_visible()
    contenu = price_block.inner_text()
    assert fragment_en in contenu or fragment_fr in contenu, (
        f"Le bloc tarif devrait contenir '{fragment_en}' ou '{fragment_fr}', "
        f"got: {contenu!r}"
    )


class TestReservationLimits:
    """Limites de réservation / Reservation limits."""

    def test_stock_max_and_membership_messages(
        self, page, browser, api_key, create_event, create_product, login_as,
        django_shell,
    ):
        """Vérifie les messages : stock épuisé, max par tarif, max par
        événement, adhésion requise (anonyme + connecté), puis compteur
        visible une fois membre.
        / Checks the messages: out of stock, max per price, max per event,
        membership required (anonymous + logged), then counter visible once
        member.
        """
        random_id = _random_id()
        user_email = f"jturbeaux+limit{random_id}@pm.me"

        event_name = f"E2E Reservation Limits {random_id}"
        product_name = f"Billets Limits {random_id}"
        price_name = "Tarif Unique"

        max_event_name = f"E2E Event Max {random_id}"
        max_product_name = f"Billets Event Max {random_id}"

        membership_product_name = f"Adhesion Required {random_id}"
        membership_price_name = "Adhesion Tarif"
        restricted_event_name = f"E2E Reservation Restricted {random_id}"
        restricted_product_name = f"Billets Restricted {random_id}"
        restricted_price_name = "Tarif Reserve"

        start_date = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()

        # --- Étape 1 : Créer les événements et produits via API ---
        # / Step 1: Create events and products via API

        # Event 1 : stock=1 et maxPerUser=1 sur le tarif (max event large : 5)
        # / Event 1: stock=1 and maxPerUser=1 on the price (event max wide: 5)
        event_result = create_event(
            name=event_name, start_date=start_date, max_per_user=5,
        )
        assert event_result["ok"], f"Création événement échouée: {event_result}"
        event_slug = event_result["slug"]
        event_uuid = event_result["uuid"]

        product_result = create_product(
            name=product_name,
            description="Produit pour stock et max par prix.",
            category="Free booking",
            event_uuid=event_uuid,
            offers=[
                {
                    "name": price_name,
                    "price": "0.00",
                    "stock": 1,
                    "maxPerUser": 1,
                },
            ],
        )
        assert product_result["ok"], f"Création produit échouée: {product_result}"
        price_uuid = _find_offer_uuid(product_result, price_name)
        assert price_uuid, f"UUID du tarif principal manquant: {product_result}"

        # Event 2 : max 1 billet par utilisateur pour tout l'événement
        # / Event 2: max 1 ticket per user for the whole event
        max_event_result = create_event(
            name=max_event_name, start_date=start_date, max_per_user=1,
        )
        assert max_event_result["ok"], (
            f"Création événement max échouée: {max_event_result}"
        )
        max_event_slug = max_event_result["slug"]
        max_event_uuid = max_event_result["uuid"]

        max_product_result = create_product(
            name=max_product_name,
            description="Produit pour max event.",
            category="Free booking",
            event_uuid=max_event_uuid,
            offers=[
                {"name": "Tarif Event Max", "price": "0.00"},
            ],
        )
        assert max_product_result["ok"], (
            f"Création produit max échouée: {max_product_result}"
        )
        max_price_uuid = _find_offer_uuid(max_product_result, "Tarif Event Max")
        assert max_price_uuid, f"UUID du tarif max manquant: {max_product_result}"

        # Event 3 : tarif réservé aux adhérents d'un produit adhésion
        # / Event 3: price restricted to members of a membership product
        restricted_event_result = create_event(
            name=restricted_event_name, start_date=start_date,
        )
        assert restricted_event_result["ok"], (
            f"Création événement restreint échouée: {restricted_event_result}"
        )
        restricted_event_slug = restricted_event_result["slug"]

        membership_product_result = create_product(
            name=membership_product_name,
            description="Adhesion de test.",
            category="Membership",
            offers=[
                {"name": membership_price_name, "price": "10.00"},
            ],
        )
        assert membership_product_result["ok"], (
            f"Création adhésion échouée: {membership_product_result}"
        )
        membership_price_uuid = _find_offer_uuid(
            membership_product_result, membership_price_name
        )
        assert membership_price_uuid, (
            f"UUID du tarif adhésion manquant: {membership_product_result}"
        )
        membership_product_uuid = membership_product_result["uuid"]
        assert membership_product_uuid, (
            f"UUID du produit adhésion manquant: {membership_product_result}"
        )

        restricted_product_result = _create_restricted_product(
            api_key,
            name=restricted_product_name,
            description="Produit avec adhesion obligatoire.",
            event_uuid=restricted_event_result["uuid"],
            offer_name=restricted_price_name,
            membership_product_uuid=membership_product_uuid,
        )
        assert restricted_product_result["ok"], (
            f"Création produit restreint échouée: {restricted_product_result}"
        )

        # --- Étape 2 : Créer les réservations via API ---
        # Le user consomme le stock (event 1) et son quota (event 2).
        # / Step 2: Create reservations via API. The user consumes the stock
        # (event 1) and their quota (event 2).
        res1 = _create_reservation(
            api_key, event_uuid, user_email, price_uuid, qty=1, confirmed=True,
        )
        assert res1["ok"], f"Réservation 1 échouée: {res1}"

        res2 = _create_reservation(
            api_key, max_event_uuid, user_email, max_price_uuid,
            qty=1, confirmed=True,
        )
        assert res2["ok"], f"Réservation 2 échouée: {res2}"

        # --- Étape 3 : Anonyme voit le stock épuisé ---
        # La fixture `page` démarre sans cookie de session : anonyme.
        # / Step 3: Anonymous sees out of stock. The `page` fixture starts
        # without a session cookie: anonymous.
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        _open_booking_panel(page)
        _expect_price_block_text(
            _price_block(page, price_name),
            "no longer available",
            "n'est plus disponible",
        )

        # --- Étape 4 : Connecté voit le max par tarif atteint ---
        # L'API réservation crée le user avec is_active=False. force_login +
        # ModelBackend rejette les users inactifs sur les requêtes suivantes
        # (PIEGES.md 9.88) : la page serait servie comme anonyme et montrerait
        # le message de stock épuisé. Le flow TS `loginAs` passait par le lien
        # email TEST MODE qui activait le compte — on reproduit l'activation
        # en DB avant le login (même pattern que test_user_account_summary).
        # NB : pas de guillemets doubles dans le code shell (échappement conftest).
        # / Step 4: Logged user sees max per price reached.
        # The reservation API creates the user with is_active=False. force_login
        # + ModelBackend rejects inactive users on subsequent requests (see
        # PIEGES.md 9.88): the page would render as anonymous and show the
        # out-of-stock message. The TS `loginAs` flow used the TEST MODE email
        # link which activated the account — we replicate that activation in DB
        # before logging in (same pattern as test_user_account_summary).
        shell_output = django_shell(
            "from django.contrib.auth import get_user_model; "
            f"get_user_model().objects.filter(email__iexact='{user_email}')"
            ".update(is_active=True); "
            "print('USER_ACTIVATED')"
        )
        assert "USER_ACTIVATED" in shell_output, (
            f"Activation du user échouée: {shell_output}"
        )

        login_as(page, user_email)
        page.goto(f"/event/{event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        _open_booking_panel(page)
        _expect_price_block_text(
            _price_block(page, price_name),
            "maximum number of reservations",
            "nombre maximum de réservations",
        )

        # --- Étape 5 : Message max par événement ---
        # Le user a déjà 1 billet sur l'event max (maxPerUser=1) : la page
        # event affiche directement le message de quota atteint.
        # / Step 5: Event max per user message. The user already holds 1
        # ticket on the max event (maxPerUser=1): the event page shows the
        # quota-reached message directly.
        page.goto(f"/event/{max_event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        page_text = page.text_content("body") or ""
        assert (
            "maximum number of tickets" in page_text
            or "nombre maximum de réservations" in page_text
        ), (
            "La page devrait afficher le message de maximum de billets, "
            f"got: {page_text[:500]!r}"
        )

        # --- Étape 6 : Messages anonyme et non-membre sur le tarif réservé ---
        # Contexte navigateur séparé pour l'anonyme : `page` est déjà loggée.
        # / Step 6: Anonymous and non-member messages on the restricted price.
        # Separate browser context for the anonymous user: `page` is logged in.
        anon_context = browser.new_context(
            base_url=BASE_URL, ignore_https_errors=True,
        )
        try:
            anon_page = anon_context.new_page()
            anon_page.goto(f"/event/{restricted_event_slug}/")
            anon_page.wait_for_load_state("domcontentloaded")
            _open_booking_panel(anon_page)
            _expect_price_block_text(
                _price_block(anon_page, restricted_price_name),
                "Log in to access this rate",
                "Connectez-vous pour accéder à ce tarif",
            )
        finally:
            anon_context.close()

        # Le user connecté n'est pas encore membre : message d'adhésion requise.
        # / The logged user is not a member yet: membership required message.
        page.goto(f"/event/{restricted_event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        _open_booking_panel(page)
        _expect_price_block_text(
            _price_block(page, restricted_price_name),
            "to book this rate",
            "pour réserver à ce tarif",
        )

        # --- Étape 7 : Une fois membre, le compteur est visible ---
        # / Step 7: Once member, the counter is visible
        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=30)
        ).isoformat()
        membership_result = _create_membership(
            api_key, membership_price_uuid, user_email, valid_until,
        )
        assert membership_result["ok"], (
            f"Création adhésion user échouée: {membership_result}"
        )

        page.goto(f"/event/{restricted_event_slug}/")
        page.wait_for_load_state("domcontentloaded")
        _open_booking_panel(page)
        restricted_block = _price_block(page, restricted_price_name)
        counter = restricted_block.locator("bs-counter")
        expect(counter).to_be_visible()
